# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for the buffered-Voronoi-cell collision avoidance geometry."""

import math

from dotbot.sdk.avoid import bvc_waypoint, safe_hop

ARENA = (3000, 3000)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_goal_through_neighbor_stops_at_buffered_bisector():
    pos = {"A": (1000.0, 1500.0), "B": (2000.0, 1500.0)}
    wp = bvc_waypoint("A", pos, (2500.0, 1500.0), ARENA, max_step=10000)
    # midpoint is x=1500, buffer 150 -> the waypoint may not pass x=1350
    assert abs(wp[0] - 1350) < 1
    assert abs(wp[1] - 1500) < 1


def test_goal_inside_own_cell_is_returned_unchanged():
    pos = {"A": (1000.0, 1500.0), "B": (2000.0, 1500.0)}
    assert bvc_waypoint("A", pos, (1200.0, 1200.0), ARENA, max_step=10000) == (
        1200.0,
        1200.0,
    )


def test_max_step_caps_the_hop():
    pos = {"A": (1000.0, 1500.0), "B": (2000.0, 1500.0)}
    wp = bvc_waypoint("A", pos, (2500.0, 1500.0), ARENA, max_step=100)
    assert dist(wp, pos["A"]) <= 100.001


def test_goal_outside_arena_is_clamped_to_wall_margin():
    pos = {"A": (2800.0, 1500.0), "B": (1000.0, 1000.0)}
    wp = bvc_waypoint("A", pos, (3500.0, 1500.0), ARENA, max_step=10000)
    assert wp[0] <= 2850.0  # 3000 - wall margin


def test_intruders_flee_apart_never_toward():
    pos = {"A": (1500.0, 1500.0), "B": (1620.0, 1500.0)}
    wa = bvc_waypoint("A", pos, (2500.0, 1500.0), ARENA)
    wb = bvc_waypoint("B", pos, (500.0, 1500.0), ARENA)
    assert wa[0] < 1500.0  # A moves away from B even though its goal is past B
    assert wb[0] > 1620.0


def test_recovery_still_respects_other_neighbors():
    # A has an intruder B to the east and a well-spaced C to the west:
    # fleeing B must not cross C's buffered bisector.
    pos = {"A": (1500.0, 1500.0), "B": (1600.0, 1500.0), "C": (1100.0, 1500.0)}
    wp = bvc_waypoint("A", pos, (2500.0, 1500.0), ARENA)
    assert wp[0] >= 1449.0  # bisector at 1300 + 150 buffer


def test_waypoints_of_two_bots_never_violate_the_floor():
    # For any pair both heading at each other, commanded waypoints stay
    # >= 2*safe_radius apart - the BVC invariant the demos rely on.
    pos = {"A": (1200.0, 1500.0), "B": (1800.0, 1500.0)}
    wa = bvc_waypoint("A", pos, pos["B"], ARENA)
    wb = bvc_waypoint("B", pos, pos["A"], ARENA)
    assert dist(wa, wb) >= 300.0 - 1e-6


def test_safe_hop_aligned_returns_plain_waypoint():
    pos = {"A": (1000.0, 1500.0), "B": (2600.0, 1500.0)}
    goal = (1000.0, 2000.0)  # straight +y, heading 0 = +y -> aligned
    assert safe_hop("A", pos, goal, ARENA, heading=0.0) == bvc_waypoint(
        "A", pos, goal, ARENA
    )


def test_safe_hop_misaligned_in_crowd_yields_to_lower_address():
    # B is 280 mm from A (inside floor+yield gap); A points away from its hop.
    pos = {"B": (1500.0, 1500.0), "C": (1780.0, 1500.0)}
    # C's hop points -x ... heading +x (=-90 in firmware frame is +x; 90 is -x)
    wp = safe_hop("C", pos, (2500.0, 1500.0), ARENA, heading=90.0)
    assert wp == pos["C"]  # yields: stop in place


def test_safe_hop_misaligned_mover_takes_short_bites():
    pos = {"B": (1500.0, 1500.0), "C": (1780.0, 1500.0)}
    # B is the lowest address, so it moves - but it faces +x (heading -90)
    # while its hop points -x, so the hop is capped to a short bite.
    wp = safe_hop("B", pos, (500.0, 1500.0), ARENA, heading=-90.0, yield_ok=True)
    hop = dist(wp, pos["B"])
    assert 0 < hop <= 80.001


def test_safe_hop_yield_override_lets_the_stuck_bot_move():
    pos = {"B": (1500.0, 1500.0), "C": (1780.0, 1500.0)}
    wp = safe_hop("C", pos, (2500.0, 1500.0), ARENA, heading=90.0, yield_ok=False)
    assert wp != pos["C"]


def test_boxed_in_bot_stands_still():
    pos = {
        "A": (1500.0, 1500.0),
        "N": (1500.0, 1720.0),
        "S": (1500.0, 1280.0),
        "E": (1720.0, 1500.0),
        "W": (1280.0, 1500.0),
    }
    wp = bvc_waypoint("A", pos, (2500.0, 1500.0), ARENA)
    assert dist(wp, pos["A"]) < 1e-6
