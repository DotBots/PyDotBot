# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for the buffered-Voronoi-cell collision avoidance geometry."""

import math

from dotbot.swarm.avoid import bvc_waypoint, safe_hop

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


def test_duplicate_positions_do_not_crash():
    # Real LH2 feeds can report two bots at the same coordinates; the clip
    # must tolerate the degenerate geometry instead of dividing by zero.
    pos = {
        "A": (1500.0, 1500.0),
        "B": (1700.0, 1500.0),
        "C": (1700.0, 1500.0),  # duplicate of B
        "D": (1500.0, 1700.0),
    }
    wp = bvc_waypoint("A", pos, (2500.0, 2500.0), ARENA)
    assert math.isfinite(wp[0]) and math.isfinite(wp[1])


# ---- Bot position gating (real-LH2 tolerance) -------------------------------

from dotbot.models import DotBotLH2Position, DotBotModel  # noqa: E402
from dotbot.swarm.bot import Bot  # noqa: E402


def _model(x=None, y=None, direction=0):
    lh2 = None if x is None else DotBotLH2Position(x=x, y=y, z=0)
    return DotBotModel(
        address="aaaa", last_seen=0, lh2_position=lh2, direction=direction
    )


def test_zero_zero_fix_is_not_a_position():
    bot = Bot(None, _model(0, 0, direction=-1000))
    assert bot.position is None
    assert bot.direction is None


def test_glitch_jump_is_held_until_confirmed():
    bot = Bot(None, _model(1000, 1000))
    assert (bot.position.x, bot.position.y) == (1000, 1000)
    bot._apply(_model(2500, 1000))  # implies an impossible speed
    assert (bot.position.x, bot.position.y) == (1000, 1000)  # held
    bot._apply(_model(2510, 1000))  # second consistent report: accepted
    assert (bot.position.x, bot.position.y) == (2510, 1000)


def test_lost_fix_keeps_last_known_position():
    bot = Bot(None, _model(1000, 1000))
    bot._apply(_model(0, 0, direction=-1000))  # fix lost mid-run
    assert (bot.position.x, bot.position.y) == (1000, 1000)


# ---- Swarm event semantics ---------------------------------------------------

from dotbot.swarm.events import BatteryUpdate  # noqa: E402
from dotbot.swarm.swarm import Swarm  # noqa: E402


def _bat_model(battery):
    return DotBotModel(address="aaaa", last_seen=0, battery=battery)


def test_battery_update_compares_against_last_emitted():
    swarm = Swarm(object())
    bot = Bot(swarm, _bat_model(3.0))
    swarm._bots[bot.address] = bot
    got = []
    swarm.on(BatteryUpdate, lambda e: got.append(e.battery))
    # First report emits; then a slow drain in 0.01 V steps must emit again
    # once the cumulative drop from the last *emitted* value reaches 0.05.
    for v in (3.0, 2.99, 2.98, 2.97, 2.96, 2.95, 2.94):
        before = (bot.position, bot.battery, bot.mode, bot._status)
        bot._apply(_bat_model(v))
        swarm._emit_changes(bot, *before)
    assert got[0] == 3.0
    assert len(got) >= 2  # the drain crossed the threshold exactly once
    assert got[1] <= 2.95


def test_raising_handler_does_not_break_other_handlers():
    swarm = Swarm(object())
    bot = Bot(swarm, _bat_model(3.0))
    swarm._bots[bot.address] = bot
    seen = []

    def bad(_event):
        raise RuntimeError("user bug")

    swarm.on(BatteryUpdate, bad)
    swarm.on(BatteryUpdate, lambda e: seen.append(e))
    before = (bot.position, bot.battery, bot.mode, bot._status)
    bot._apply(_bat_model(2.0))
    swarm._emit_changes(bot, *before)  # must not raise
    assert len(seen) == 1
