# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Shared helpers for the sdk_demo set.

Every geometric quantity (centre, rings, bearings) is computed from the *live*
fleet positions, never hardcoded, so the same demo runs unchanged in the
simulator and on the real testbed regardless of arena size or where the bots
happen to sit.
"""

from __future__ import annotations

import asyncio
import colorsys
import math

from dotbot.swarm import Position, Swarm, avoid


async def settle(swarm: Swarm, seconds: float = 1.5) -> list:
    """Wait for the first ws/status round to arrive, then return the bots that
    have a position fix, sorted by address (stable order across runs)."""
    await asyncio.sleep(seconds)
    bots = positioned(swarm)
    print(f"{len(bots)}/{len(swarm)} bots have a position fix")
    return bots


def positioned(swarm: Swarm) -> list:
    """The bots that currently have an LH2 fix, ordered by address."""
    return sorted(
        (b for b in swarm if b.position is not None), key=lambda b: b.address
    )


def centroid(bots: list) -> Position:
    """The mean position of the fleet - its live centre."""
    n = len(bots)
    return Position(
        sum(b.position.x for b in bots) / n,
        sum(b.position.y for b in bots) / n,
    )


def max_radius(bots: list, center: Position) -> float:
    return max(b.position.distance_to(center) for b in bots)


def make_rings(bots: list, center: Position, n_rings: int) -> list:
    """Bucket bots into `n_rings` concentric rings by distance from `center`
    (ring 0 = innermost, ring n-1 = outermost edge)."""
    r_max = max_radius(bots, center) or 1.0
    rings: list = [[] for _ in range(n_rings)]
    for b in bots:
        frac = b.position.distance_to(center) / r_max
        rings[min(int(frac * n_rings), n_rings - 1)].append(b)
    return rings


def angle_deg(bot, center: Position) -> float:
    """Bearing of a bot from `center`, in degrees."""
    return math.degrees(
        math.atan2(bot.position.y - center.y, bot.position.x - center.x)
    )


def rotate(p: Position, center: Position, deg: float) -> Position:
    """Rotate point `p` about `center` by `deg` degrees (counter-clockwise)."""
    rad = math.radians(deg)
    dx, dy = p.x - center.x, p.y - center.y
    return Position(
        center.x + dx * math.cos(rad) - dy * math.sin(rad),
        center.y + dx * math.sin(rad) + dy * math.cos(rad),
    )


def hsv(h: float, s: float = 1.0, v: float = 1.0) -> tuple:
    """HSV (h wrapped into [0, 1)) -> (r, g, b) ints 0..255 for set_color()."""
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


# ---- collision-aware driving (buffered Voronoi cells) -----------------------
#
# Targets alone don't avoid collisions: a bot drives a straight-ish arc to its
# waypoint regardless of who is in the way. The geometry that fixes this lives
# in `dotbot.swarm.avoid` (the SDK's composable low-level rung; the built-in
# counterpart is `Swarm.connect(..., collision_avoidance=True)`). These demos
# drive it by hand through the drive() loop below, doubling as reference code
# for anyone writing their own control loop.

SAFE_RADIUS = avoid.DEFAULT_SAFE_RADIUS  # mm: half the minimum separation
WALL_MARGIN = avoid.DEFAULT_WALL_MARGIN  # mm: waypoints stay off the walls
MAX_STEP = avoid.DEFAULT_MAX_STEP  # mm: longest hop commanded per tick
ARRIVE = 120.0  # mm: a bot this close to its goal is done
DRIVE_TICK = 1.0  # s between waypoint updates (~1 cmd/s/bot link budget)
SIDESTEP = 200.0  # mm: detour length when stuck (right-hand rule)
PLAN_BUDGET_HZ = 60.0  # cmd/s a drive loop may consume (Mari gateway does ~80)


def pace_tick(n_bots: int, base: float = DRIVE_TICK) -> float:
    """The tick that keeps `n_bots` one-command-per-tick loops inside the
    gateway downlink budget: at 16 bots the base tick stands; at 100+ bots
    the loop slows down instead of flooding the link."""
    return max(base, n_bots / PLAN_BUDGET_HZ)


MIN_HOP_THRESHOLD = 60  # mm: don't chase precision below the LH2 noise floor


def hop_goto(bot, wp: tuple, px: float, py: float) -> None:
    """Send a shepherd hop, working around the firmware arrival rule: a
    waypoint within the threshold is "already reached" and moves nothing, so
    short hops are sent with a scaled-down threshold - but never below the
    LH2 noise floor, where a real bot circles a target it can't resolve."""
    hop = math.hypot(wp[0] - px, wp[1] - py)
    if hop < MIN_HOP_THRESHOLD:
        return
    threshold = 100 if hop >= 250 else max(MIN_HOP_THRESHOLD, int(hop * 0.5))
    bot.goto(*wp, threshold=threshold)


def safe_hop(
    bot,
    positions: dict,
    goal: tuple,
    arena: tuple,
    *,
    safe_radius: float = SAFE_RADIUS,
    yield_ok: bool = True,
) -> tuple:
    """`dotbot.swarm.avoid.safe_hop` with the heading read off the live Bot."""
    return avoid.safe_hop(
        bot.address,
        positions,
        goal,
        arena,
        heading=getattr(bot, "direction", None),
        yield_ok=yield_ok,
        safe_radius=safe_radius,
    )


async def drive(
    bots: list,
    goals: dict,
    arena: tuple,
    *,
    arrive: float = ARRIVE,
    timeout: float = 45.0,
    safe_radius: float = SAFE_RADIUS,
    tick: float = DRIVE_TICK,
) -> set:
    """Shepherd every bot to its goal collision-free and return the addresses
    that arrived. Each tick, every unarrived bot is sent the safe waypoint
    toward its goal (BVC projection); a bot that stops making progress while
    blocked detours to its right for a tick (the standard BVC deadlock
    heuristic). Gives up on stragglers after `timeout` rather than hanging."""
    pending = {b.address for b in bots if b.address in goals}
    last_pos: dict = {}
    stuck: dict = {}
    contact: dict = {}
    tick = pace_tick(len(pending), tick)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while pending and loop.time() < deadline:
        positions = {
            b.address: (b.position.x, b.position.y) for b in bots if b.position
        }
        for b in bots:
            a = b.address
            if a not in pending or a not in positions:
                continue
            if not b.is_online:
                continue  # crashed/lost: stop sending, keep it as an obstacle
            px, py = positions[a]
            gx, gy = goals[a]
            if math.hypot(gx - px, gy - py) <= arrive:
                pending.discard(a)
                continue
            # Contact guard: pinned against a neighbour -> stop, don't grind.
            nearest = min(
                (
                    math.hypot(qx - px, qy - py)
                    for o, (qx, qy) in positions.items()
                    if o != a
                ),
                default=float("inf"),
            )
            if nearest < 130:
                contact[a] = contact.get(a, 0) + 1
                if contact[a] >= 3:
                    print(f"  contact stop {a[-4:]} (neighbour at {nearest:.0f} mm)")
                    pending.discard(a)
                    b.stop()
                    continue
            else:
                contact.pop(a, None)
            if a in last_pos and math.hypot(px - last_pos[a][0], py - last_pos[a][1]) < 25:
                stuck[a] = stuck.get(a, 0) + 1
            else:
                stuck[a] = 0
            goal = (gx, gy)
            patience = stuck.get(a, 0)
            if patience >= 3:  # blocked: detour to the right of the goal line
                d = math.hypot(gx - px, gy - py) or 1.0
                ux, uy = (gx - px) / d, (gy - py) / d
                goal = (px + uy * SIDESTEP, py - ux * SIDESTEP)
                stuck[a] = 0
            wp = safe_hop(
                b, positions, goal, arena,
                safe_radius=safe_radius, yield_ok=patience < 2,
            )
            hop_goto(b, wp, px, py)
            last_pos[a] = (px, py)
        await asyncio.sleep(tick)
    if pending:
        positions = {
            b.address: (b.position.x, b.position.y) for b in bots if b.position
        }
        by_addr = {b.address: b for b in bots}
        for a in sorted(pending):
            if a in positions and a in goals:
                px, py = positions[a]
                d = math.hypot(goals[a][0] - px, goals[a][1] - py)
                wp = safe_hop(by_addr[a], positions, goals[a], arena, safe_radius=safe_radius)
                hop = math.hypot(wp[0] - px, wp[1] - py)
                direction = getattr(by_addr[a], "direction", None)
                print(
                    f"  straggler {a[-4:]}: {d:.0f} mm from goal "
                    f"(hop {hop:.0f} mm, heading {direction})"
                )
    return {b.address for b in bots if b.address in goals} - pending
