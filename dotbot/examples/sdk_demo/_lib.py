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

from dotbot.sdk import Position, Swarm


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
# waypoint regardless of who is in the way. The fix is to shepherd each bot
# through intermediate waypoints that always stay inside its *buffered Voronoi
# cell* (Zhou/Wang/Bandyopadhyay/Schwager, RA-L 2017): the region closer to
# this bot than to any neighbour, shrunk by a safety radius. Cells are disjoint
# by construction, so as long as every bot only ever heads to a point inside
# its own current cell, no two bots can meet - using positions only, which is
# all the 2 Hz LH2 feed gives us.

SAFE_RADIUS = 150.0  # mm: half the minimum allowed centre-to-centre distance
WALL_MARGIN = 150.0  # mm: keep waypoints this far from the arena walls
MAX_STEP = 180.0  # mm: longest hop commanded per tick (limits overshoot)
ARRIVE = 120.0  # mm: a bot this close to its goal is done
DRIVE_TICK = 1.0  # s between waypoint updates (~1 cmd/s/bot link budget)
SIDESTEP = 200.0  # mm: detour length when stuck (right-hand rule)
PLAN_BUDGET_HZ = 60.0  # cmd/s a drive loop may consume (Mari gateway does ~80)


def pace_tick(n_bots: int, base: float = DRIVE_TICK) -> float:
    """The tick that keeps `n_bots` one-command-per-tick loops inside the
    gateway downlink budget: at 16 bots the base tick stands; at 100+ bots
    the loop slows down instead of flooding the link."""
    return max(base, n_bots / PLAN_BUDGET_HZ)


def _clip_polygon(poly: list, ax: float, ay: float, c: float) -> list:
    """Clip a convex polygon to the half-plane ax*x + ay*y <= c."""
    out: list = []
    for i, cur in enumerate(poly):
        nxt = poly[(i + 1) % len(poly)]
        cur_in = ax * cur[0] + ay * cur[1] <= c
        nxt_in = ax * nxt[0] + ay * nxt[1] <= c
        if cur_in:
            out.append(cur)
        if cur_in != nxt_in:
            denom = ax * (nxt[0] - cur[0]) + ay * (nxt[1] - cur[1])
            t = (c - ax * cur[0] - ay * cur[1]) / denom
            out.append((cur[0] + t * (nxt[0] - cur[0]), cur[1] + t * (nxt[1] - cur[1])))
    return out


def _closest_in_polygon(poly: list, gx: float, gy: float) -> tuple:
    """The point of a convex polygon closest to (gx, gy)."""
    inside = len(poly) >= 3
    for i, cur in enumerate(poly):
        if not inside:
            break
        nxt = poly[(i + 1) % len(poly)]
        ex, ey = nxt[0] - cur[0], nxt[1] - cur[1]
        # CCW polygon: interior is left of every edge; right of one = outside.
        if ex * (gy - cur[1]) - ey * (gx - cur[0]) < 0:
            inside = False
    if inside:
        return (gx, gy)
    best, best_d2 = poly[0], float("inf")
    for i, cur in enumerate(poly):
        nxt = poly[(i + 1) % len(poly)]
        ex, ey = nxt[0] - cur[0], nxt[1] - cur[1]
        e2 = ex * ex + ey * ey
        t = 0.0 if e2 < 1e-12 else max(
            0.0, min(1.0, ((gx - cur[0]) * ex + (gy - cur[1]) * ey) / e2)
        )
        px, py = cur[0] + t * ex, cur[1] + t * ey
        d2 = (gx - px) ** 2 + (gy - py) ** 2
        if d2 < best_d2:
            best, best_d2 = (px, py), d2
    return best


def bvc_waypoint(
    me: str,
    positions: dict,
    goal: tuple,
    arena: tuple,
    *,
    safe_radius: float = SAFE_RADIUS,
    max_step: float = MAX_STEP,
) -> tuple:
    """The next safe waypoint for bot `me`: its goal projected into its
    buffered Voronoi cell (and inside the walls), at most `max_step` away.

    `positions` is {address: (x, y)} for every positioned bot, `arena` is
    (width, height). If a neighbour is already closer than 2*safe_radius the
    cell is empty there - fall back to stepping directly away from it.
    """
    px, py = positions[me]
    w, h = arena
    lo_x, hi_x = WALL_MARGIN, w - WALL_MARGIN
    lo_y, hi_y = WALL_MARGIN, h - WALL_MARGIN
    poly: list = [(lo_x, lo_y), (hi_x, lo_y), (hi_x, hi_y), (lo_x, hi_y)]

    # Intruders are neighbours already inside the 2*safe_radius floor (their
    # bisector plane would exclude our own position). For them we keep a weaker
    # but always-feasible constraint - never step *toward* them - and aim the
    # goal straight away from their net push instead of at the user goal.
    flee_x = flee_y = 0.0
    intruders = 0
    for other, (qx, qy) in positions.items():
        if other == me:
            continue
        dx, dy = qx - px, qy - py
        d = math.hypot(dx, dy)
        if d < 1e-9:
            continue  # exactly stacked: no direction; neighbours will pull apart
        nx, ny = dx / d, dy / d
        if d < 2 * safe_radius:
            intruders += 1
            flee_x -= dx / (d * d)
            flee_y -= dy / (d * d)
            poly = _clip_polygon(poly, nx, ny, nx * px + ny * py)  # no approach
        else:
            c = nx * (px + qx) / 2 + ny * (py + qy) / 2 - safe_radius
            poly = _clip_polygon(poly, nx, ny, c)
        if not poly:
            break

    if not poly:
        # Fully boxed in: stand still until the neighbours clear.
        return (min(max(px, lo_x), hi_x), min(max(py, lo_y), hi_y))

    if intruders:
        mag = math.hypot(flee_x, flee_y)
        if mag < 1e-9:
            return (min(max(px, lo_x), hi_x), min(max(py, lo_y), hi_y))
        goal = (px + flee_x / mag * max_step, py + flee_y / mag * max_step)

    zx, zy = _closest_in_polygon(poly, *goal)
    dx, dy = zx - px, zy - py
    d = math.hypot(dx, dy)
    if d > max_step:
        zx, zy = px + dx / d * max_step, py + dy / d * max_step
    return (zx, zy)


YIELD_GAP = 60.0  # mm above the floor within which a misaligned bot yields


def hop_goto(bot, wp: tuple, px: float, py: float) -> None:
    """Send a shepherd hop, working around the firmware arrival rule: a
    waypoint within the threshold is "already reached" and moves nothing, so
    short hops are sent with a small threshold (and micro-hops not at all)."""
    hop = math.hypot(wp[0] - px, wp[1] - py)
    if hop < 15:
        return
    threshold = 100 if hop >= 250 else max(20, int(hop * 0.5))
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
    """`bvc_waypoint` with the bot's advertised heading taken into account: a
    DotBot commanded to a point behind it arcs forward while it turns (the
    firmware never pivots in place), and that arc is what the straight-segment
    safety argument cannot see. So when the hop points far off the current
    heading AND a neighbour is at (or barely above) the safety floor, the bot
    yields - stops for the tick - unless it is the lowest address of that
    group. The mover turns with room to arc; the yielders resume as soon as
    it clears. A yielded bot never turns (it is not moving), so callers that
    track progress pass `yield_ok=False` after a few stalled ticks to let it
    creep out - by then its neighbours are stationary, the safe case for an
    arc."""
    address = bot.address
    px, py = positions[address]
    wp = bvc_waypoint(address, positions, goal, arena, safe_radius=safe_radius)
    direction = getattr(bot, "direction", None)
    if direction is None:
        return wp
    vx, vy = wp[0] - px, wp[1] - py
    if math.hypot(vx, vy) < 1.0:
        return wp
    bearing = -math.degrees(math.atan2(vx, vy))  # firmware frame: 0 = +y
    err = (bearing - direction + 180) % 360 - 180
    if abs(err) <= 60:
        return wp
    crowd = [
        a
        for a, (qx, qy) in positions.items()
        if a != address
        and math.hypot(qx - px, qy - py) < 2 * safe_radius + YIELD_GAP
    ]
    if yield_ok and crowd and min(crowd) < address:
        return (px, py)  # yield this tick; a goto to here is a stop
    if crowd:
        # Crowded and turning: take the turn in short bites so the arc the
        # firmware sweeps before it faces the hop stays small.
        hop = math.hypot(vx, vy)
        if hop > 80.0:
            wp = (px + vx / hop * 80.0, py + vy / hop * 80.0)
    return wp


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
            px, py = positions[a]
            gx, gy = goals[a]
            if math.hypot(gx - px, gy - py) <= arrive:
                pending.discard(a)
                continue
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
