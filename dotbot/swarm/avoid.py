# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Collision avoidance - buffered Voronoi cells over position-only feedback.

The algorithm is the buffered Voronoi cell (BVC) method (Zhou, Wang,
Bandyopadhyay, Schwager, RA-L 2017): each bot may only head to points closer
to itself than to any neighbour, with the boundary pulled in by a safety
radius. Cells are disjoint by construction, so as long as every bot only ever
steps inside its own current cell, no two bots can meet. It needs exactly what
a DotBot fleet provides - neighbour *positions* at ~2 Hz, no velocity
estimates - and it produces exactly what a DotBot consumes: one waypoint.

Two layers, by design:

- These pure functions (`bvc_waypoint`, `safe_hop`) are the low-level rung:
  call them from your own control loop, swap in your own planner, or study
  them as reference. Nothing here touches the network.
- `Swarm.connect(..., collision_avoidance=True)` is the high-level rung: the
  SDK then routes every `goto` / `move_to` / `follow` through a shepherd that
  streams these safe hops for you (see `dotbot.swarm._shepherd`). Its
  `min_separation` is the centre-to-centre distance between two bots, i.e.
  `min_separation = 2 * safe_radius` in the functions here.

Real-robot grounding baked into the defaults: a DotBot is ~120 mm across and
arcs while it turns (the firmware steers differentially, it never pivots in
place), positions arrive at ~2 Hz and commands take effect ~200-300 ms after
they are sent. The safety radius must absorb all of that between two hops.
"""

from __future__ import annotations

import math

# Defaults, in mm. min separation between two bots is 2 * DEFAULT_SAFE_RADIUS;
# the DotBot body envelope is ~120 mm, the rest is margin for the 2 Hz
# position staleness and the turning arc.
DEFAULT_SAFE_RADIUS = 150.0
DEFAULT_WALL_MARGIN = 150.0
DEFAULT_MAX_STEP = 180.0  # longest hop per tick; bounds overshoot past stale data
YIELD_GAP = 60.0  # mm above the floor within which a misaligned bot yields
TURN_BITE = 80.0  # mm hop cap while turning near a crowd (the arc stays small)


def _clip_polygon(poly: list, ax: float, ay: float, c: float) -> list:
    """Clip a convex polygon (CCW vertex list) to the half-plane
    ax*x + ay*y <= c."""
    out: list = []
    for i, cur in enumerate(poly):
        nxt = poly[(i + 1) % len(poly)]
        cur_in = ax * cur[0] + ay * cur[1] <= c
        nxt_in = ax * nxt[0] + ay * nxt[1] <= c
        if cur_in:
            out.append(cur)
        if cur_in != nxt_in:
            denom = ax * (nxt[0] - cur[0]) + ay * (nxt[1] - cur[1])
            if abs(denom) < 1e-12:
                # Degenerate edge (duplicate vertices or parallel to the clip
                # line, e.g. from noisy duplicate positions): nothing to cut.
                continue
            t = (c - ax * cur[0] - ay * cur[1]) / denom
            out.append((cur[0] + t * (nxt[0] - cur[0]), cur[1] + t * (nxt[1] - cur[1])))
    return out


def _closest_in_polygon(poly: list, gx: float, gy: float) -> tuple:
    """The point of a convex polygon (CCW) closest to (gx, gy)."""
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
        t = (
            0.0
            if e2 < 1e-12
            else max(0.0, min(1.0, ((gx - cur[0]) * ex + (gy - cur[1]) * ey) / e2))
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
    safe_radius: float = DEFAULT_SAFE_RADIUS,
    wall_margin: float = DEFAULT_WALL_MARGIN,
    max_step: float = DEFAULT_MAX_STEP,
) -> tuple:
    """The next safe waypoint for bot `me`: its goal projected into its
    buffered Voronoi cell (and inside the walls), at most `max_step` away.

    `positions` is {address: (x, y)} for every positioned bot (including
    `me`), `arena` is (width, height) in mm. Neighbours already inside the
    2*safe_radius floor get a weaker but always-feasible constraint - never
    step *toward* them - and the goal becomes "straight away from their net
    push"; a fully boxed-in bot is told to stand still until they clear.
    """
    px, py = positions[me]
    w, h = arena
    lo_x, hi_x = wall_margin, w - wall_margin
    lo_y, hi_y = wall_margin, h - wall_margin
    poly: list = [(lo_x, lo_y), (hi_x, lo_y), (hi_x, hi_y), (lo_x, hi_y)]

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


def safe_hop(
    me: str,
    positions: dict,
    goal: tuple,
    arena: tuple,
    *,
    heading: float | None = None,
    yield_ok: bool = True,
    safe_radius: float = DEFAULT_SAFE_RADIUS,
    wall_margin: float = DEFAULT_WALL_MARGIN,
    max_step: float = DEFAULT_MAX_STEP,
) -> tuple:
    """`bvc_waypoint` with the bot's heading taken into account.

    A DotBot commanded to a point behind it arcs forward while it turns (the
    firmware never pivots in place), and that arc is what the straight-segment
    safety argument cannot see. So when the hop points far off the current
    `heading` (firmware frame: degrees, 0 = +y) and a neighbour sits at or
    barely above the safety floor, the bot yields - the returned waypoint is
    its own position, i.e. a stop - unless it is the lowest address of that
    group; the designated mover takes the turn in short bites instead. A
    yielded bot never turns (it is not moving), so callers that track progress
    pass `yield_ok=False` after a few stalled ticks to let it creep out.
    """
    px, py = positions[me]
    wp = bvc_waypoint(
        me,
        positions,
        goal,
        arena,
        safe_radius=safe_radius,
        wall_margin=wall_margin,
        max_step=max_step,
    )
    if heading is None:
        return wp
    vx, vy = wp[0] - px, wp[1] - py
    hop = math.hypot(vx, vy)
    if hop < 1.0:
        return wp
    bearing = -math.degrees(math.atan2(vx, vy))  # firmware frame: 0 = +y
    err = (bearing - heading + 180) % 360 - 180
    if abs(err) <= 60:
        return wp
    crowd = [
        a
        for a, (qx, qy) in positions.items()
        if a != me and math.hypot(qx - px, qy - py) < 2 * safe_radius + YIELD_GAP
    ]
    if yield_ok and crowd and min(crowd) < me:
        return (px, py)  # yield this tick; a goto to here is a stop
    if crowd and hop > TURN_BITE:
        wp = (px + vx / hop * TURN_BITE, py + vy / hop * TURN_BITE)
    return wp
