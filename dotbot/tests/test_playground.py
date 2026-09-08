"""The playground contract: announcement, will, inputs, assignment, demos."""

import asyncio
import json
import random
import time

import httpx
import numpy as np
import pytest

from dotbot.examples.charging.charging import ANNOUNCEMENT as CHARGING
from dotbot.examples.charging.charging import (
    COOLDOWN_S,
    Cycle,
    docked,
    nearest_free,
    pads,
)
from dotbot.examples.common.playground import (
    DOTBOT_STATUS_LOST,
    Action,
    Announcement,
    Bot,
    CommandQueue,
    ControlChange,
    ControllerClient,
    GoalsInput,
    PlaygroundApp,
    Point,
    PointerSample,
    Rect,
    RectsInput,
    TextInput,
    app_topics,
    assign_targets,
    clear_message,
    coerce_control,
    overlay_badge,
    overlay_point,
    overlay_rect,
    parse_input,
    select,
    slider,
    toggle,
)
from dotbot.examples.common.raster import spare_ring, word_points
from dotbot.examples.follow.follow import ANNOUNCEMENT as FOLLOW
from dotbot.examples.follow.follow import follow_target, separation, wander_target
from dotbot.examples.goals.goals import ANNOUNCEMENT as GOALS
from dotbot.examples.goals.goals import ring_targets, split_by_proximity
from dotbot.examples.letters.letters import ANNOUNCEMENT as LETTERS
from dotbot.examples.region.region import ANNOUNCEMENT as REGION
from dotbot.examples.region.region import (
    capacity,
    fill_points,
    region_targets,
    share_by_area,
    share_by_capacity,
)
from dotbot.examples.show.show import ANNOUNCEMENT as SHOW
from dotbot.examples.show.show import (
    FIGURES,
    figure_overlay,
    formation,
    hue_by_angle,
    rgb,
)


class TestAnnouncement:
    def test_payload_carries_every_field_the_page_renders(self):
        payload = json.loads(FOLLOW.payload())
        assert payload["name"] == "follow"
        assert payload["inputs"] == ["pointer"]
        assert [c["id"] for c in payload["controls"]] == ["speed", "spread", "wander"]
        for key in ("title", "hint", "overlay", "positions", "protected", "ui"):
            assert key in payload

    def test_control_helpers_match_the_declared_schema(self):
        assert slider("speed", 0, 100, 60, unit="%") == {
            "id": "speed",
            "type": "slider",
            "min": 0,
            "max": 100,
            "value": 60,
            "unit": "%",
        }
        assert toggle("wander", True, label="Wander when idle") == {
            "id": "wander",
            "type": "toggle",
            "value": True,
            "label": "Wander when idle",
        }

    def test_defaults_come_from_the_declaration(self):
        assert FOLLOW.defaults() == {"speed": 60, "spread": 2, "wander": True}
        assert Announcement("x", "X", "").defaults() == {}

    def test_topics_are_three_under_one_base(self):
        assert app_topics("dotbot", "2F00", "follow") == (
            "dotbot/2F00/apps/follow",
            "dotbot/2F00/apps/follow/in",
            "dotbot/2F00/apps/follow/out",
        )


class TestWill:
    def test_the_will_empties_the_retained_announcement(self):
        will = clear_message("dotbot/0000/apps/follow")
        assert will.topic == b"dotbot/0000/apps/follow"
        assert will.payload == b""
        assert will.retain is True
        assert will.qos == 1


class TestParseInput:
    def test_pointer_over_the_arena(self):
        parsed = parse_input('{"kind":"pointer","client":"c1","at":{"x":10,"y":20.5}}')
        assert parsed == PointerSample(client="c1", at=Point(10.0, 20.5))

    def test_pointer_that_left_carries_null(self):
        parsed = parse_input(b'{"kind":"pointer","client":"c1","at":null}')
        assert parsed == PointerSample(client="c1", at=None)

    def test_control_change(self):
        parsed = parse_input(
            {"kind": "control", "client": "c1", "id": "speed", "value": 80}
        )
        assert parsed == ControlChange(client="c1", id="speed", value=80)

    def test_an_unmodelled_kind_arrives_as_a_plain_dict(self):
        message = {"kind": "shapes", "client": "c1", "shapes": [{"r": 40}]}
        assert parse_input(json.dumps(message)) == message

    def test_junk_is_dropped(self):
        assert parse_input("not json") is None
        assert parse_input("[1, 2]") is None
        assert parse_input('{"client":"c1"}') is None
        assert parse_input('{"kind":"pointer","at":{"x":1}}') is None
        assert parse_input('{"kind":"control","client":"c1"}') is None


class TestCommandQueue:
    def test_the_latest_target_replaces_the_one_before_it(self):
        queue = CommandQueue()
        queue.put("AA", "waypoints", {"waypoints": [{"x": 1, "y": 1}]})
        queue.put("AA", "waypoints", {"waypoints": [{"x": 2, "y": 2}]})
        assert len(queue) == 1
        assert queue.drain() == [("AA", "waypoints", {"waypoints": [{"x": 2, "y": 2}]})]

    def test_kinds_and_bots_hold_separate_slots(self):
        queue = CommandQueue()
        queue.put("AA", "waypoints", 1)
        queue.put("AA", "rgb_led", 2)
        queue.put("BB", "waypoints", 3)
        assert queue.drain() == [
            ("AA", "waypoints", 1),
            ("AA", "rgb_led", 2),
            ("BB", "waypoints", 3),
        ]

    def test_draining_empties_it(self):
        queue = CommandQueue()
        queue.put("AA", "waypoints", 1)
        queue.drain()
        assert queue.drain() == []


class TestFollowGeometry:
    ARENA = (2000, 2000)

    def test_a_lone_bot_heads_straight_at_the_pointer(self):
        target = follow_target(
            Point(500, 500),
            Point(1500, 500),
            [Point(500, 500)],
            spread_mm=160,
            step_mm=200,
            arena=self.ARENA,
        )
        assert target.y == 500
        assert 690 < target.x < 710

    def test_it_stops_on_the_pointer_rather_than_overshooting(self):
        target = follow_target(
            Point(1000, 1000),
            Point(1050, 1000),
            [Point(1000, 1000)],
            spread_mm=160,
            step_mm=400,
            arena=self.ARENA,
        )
        assert target == Point(1050.0, 1000.0)

    def test_a_crowded_bot_is_pushed_off_its_neighbours(self):
        crowd = [Point(1000, 1000), Point(1040, 1000), Point(1000, 1040)]
        target = follow_target(
            Point(1000, 1000),
            Point(1000, 1000),
            crowd,
            spread_mm=200,
            step_mm=100,
            arena=self.ARENA,
        )
        assert target.x < 1000 and target.y < 1000

    def test_targets_stay_inside_the_arena(self):
        target = follow_target(
            Point(1950, 1950),
            Point(5000, 5000),
            [Point(1950, 1950)],
            spread_mm=160,
            step_mm=400,
            arena=self.ARENA,
        )
        assert 0 <= target.x <= 2000 and 0 <= target.y <= 2000

    def test_separation_ignores_the_bot_itself_and_distant_neighbours(self):
        assert separation(Point(0, 0), [Point(0, 0)], 200) == (0.0, 0.0)
        assert separation(Point(0, 0), [Point(500, 0)], 200) == (0.0, 0.0)
        push = separation(Point(0, 0), [Point(50, 0)], 200)
        assert push[0] < 0 and abs(push[1]) < 1e-9

    def test_wander_goals_land_inside_the_arena(self):
        rng = random.Random(1)
        for _ in range(50):
            goal = wander_target(rng, self.ARENA, margin=200)
            assert 200 <= goal.x <= 1800 and 200 <= goal.y <= 1800


class TestParseTheNewInputKinds:
    def test_goals_arrive_as_points_in_the_order_they_were_placed(self):
        parsed = parse_input(
            '{"kind":"goals","client":"c1","points":[{"x":1,"y":2},{"x":3,"y":4}]}'
        )
        assert parsed == GoalsInput(client="c1", points=[Point(1, 2), Point(3, 4)])

    def test_an_emptied_goal_set_is_a_message_of_its_own(self):
        assert parse_input(
            {"kind": "goals", "client": "c1", "points": []}
        ) == GoalsInput(client="c1", points=[])

    def test_rects_carry_a_positive_width_and_height(self):
        parsed = parse_input(
            '{"kind":"rects","client":"c1","rects":[{"x":0,"y":0,"w":400,"h":200}]}'
        )
        assert parsed == RectsInput(client="c1", rects=[Rect(0, 0, 400, 200)])
        assert parsed.rects[0].area == 80000
        assert parsed.rects[0].center == Point(200, 100)

    def test_text_and_actions(self):
        assert parse_input(
            {"kind": "text", "client": "c1", "text": "DOTBOT"}
        ) == TextInput(client="c1", text="DOTBOT")
        assert parse_input({"kind": "action", "client": "c1", "id": "go"}) == Action(
            client="c1", id="go"
        )

    def test_a_malformed_set_is_dropped_whole(self):
        assert parse_input('{"kind":"goals","points":[{"x":1}]}') is None
        assert parse_input('{"kind":"goals","points":"none"}') is None
        assert parse_input('{"kind":"rects","rects":[{"x":0,"y":0,"w":1}]}') is None
        assert parse_input('{"kind":"text","text":42}') is None
        assert parse_input('{"kind":"action"}') is None


class TestOverlayItems:
    def test_each_constructor_names_its_type_and_rounds_its_geometry(self):
        assert overlay_point(10.04, 20.06, r=45.0, label="pad", color="good") == {
            "type": "point",
            "x": 10.0,
            "y": 20.1,
            "r": 45.0,
            "label": "pad",
            "color": "good",
        }
        assert overlay_rect(0, 0, 400, 200) == {
            "type": "rect",
            "x": 0,
            "y": 0,
            "w": 400,
            "h": 200,
        }
        assert overlay_badge("DEAD", "charging") == {
            "type": "badge",
            "address": "DEAD",
            "text": "charging",
        }

    def test_an_overlay_carries_only_what_was_asked_for(self):
        assert "label" not in overlay_point(1, 2)
        assert "fill" not in overlay_rect(0, 0, 1, 1)


class TestAssignTargets:
    def test_every_bot_gets_a_distinct_target(self):
        rng = np.random.default_rng(7)
        bots = rng.uniform(0, 2000, (60, 2))
        slots = rng.uniform(0, 2000, (60, 2))
        order = assign_targets(bots, slots)
        assert len(order) == 60
        assert len(set(order.tolist())) == 60

    def test_the_obvious_pairing_is_the_one_it_finds(self):
        bots = [[0, 0], [1000, 0], [0, 1000]]
        slots = [[0, 1010], [10, 0], [1010, 0]]
        assert assign_targets(bots, slots).tolist() == [1, 2, 0]

    def test_the_swap_passes_beat_greedy_alone(self):
        rng = np.random.default_rng(3)
        bots = rng.uniform(0, 2000, (80, 2))
        slots = rng.uniform(0, 2000, (80, 2))
        greedy = assign_targets(bots, slots, max_passes=0)
        swapped = assign_targets(bots, slots)
        cost = lambda order: float(((bots - slots[order]) ** 2).sum())  # noqa: E731
        assert cost(swapped) < cost(greedy)

    def test_spare_targets_are_allowed_but_missing_ones_are_not(self):
        bots = [[0, 0], [100, 0]]
        assert len(assign_targets(bots, [[0, 0], [100, 0], [200, 0]])) == 2
        with pytest.raises(ValueError):
            assign_targets(bots, [[0, 0]])

    def test_an_empty_swarm_assigns_nothing(self):
        assert len(assign_targets([], [[0, 0]])) == 0

    def test_a_thousand_bots_assign_inside_one_command_period(self):
        """A 5 Hz loop leaves 200 ms a tick, and this runs on that loop."""
        rng = np.random.default_rng(11)
        bots = rng.uniform(0, 6000, (1000, 2))
        slots = rng.uniform(0, 6000, (1000, 2))
        started = time.perf_counter()
        order = assign_targets(bots, slots)
        elapsed = time.perf_counter() - started
        assert len(set(order.tolist())) == 1000
        assert elapsed < 0.5, f"assignment took {elapsed:.3f} s"

    def test_four_times_the_fleet_does_not_cost_sixty_four_times_as_much(self):
        """Assignment is quadratic in the fleet; a scan per bot picked is cubic."""
        rng = np.random.default_rng(5)

        def timed(n):
            bots = rng.uniform(0, 6000, (n, 2))
            slots = rng.uniform(0, 6000, (n, 2))
            started = time.perf_counter()
            assign_targets(bots, slots, max_passes=0)
            return time.perf_counter() - started

        timed(250)  # warm up numpy, whose first call carries setup
        small = max(timed(250), 1e-4)
        assert timed(1000) < 30 * small


class TestRasterisedWords:
    ARENA = (6000, 6000)

    def test_dotbot_fits_the_bot_budget(self):
        for budget in (40, 80, 150):
            points = word_points(
                "DOTBOT",
                budget=budget,
                height_mm=1400,
                arena=self.ARENA,
                min_spacing_mm=160,
            )
            assert 0 < len(points) <= budget

    def test_no_two_bots_are_aimed_closer_than_two_footprints(self):
        points = word_points(
            "DOTBOT", budget=150, height_mm=1400, arena=self.ARENA, min_spacing_mm=160
        )
        gaps = np.hypot(*(points[:, None, :] - points[None, :, :]).transpose(2, 0, 1))
        np.fill_diagonal(gaps, np.inf)
        assert gaps.min() >= 160 - 1e-6

    def test_the_word_stays_inside_the_arena(self):
        points = word_points(
            "DOTBOT", budget=200, height_mm=5000, arena=self.ARENA, min_spacing_mm=160
        )
        assert points[:, 0].min() >= 0 and points[:, 0].max() <= self.ARENA[0]
        assert points[:, 1].min() >= 0 and points[:, 1].max() <= self.ARENA[1]

    def test_a_wider_word_is_sampled_more_coarsely_for_the_same_budget(self):
        one = word_points(
            "I", budget=60, height_mm=1400, arena=self.ARENA, min_spacing_mm=160
        )
        many = word_points(
            "DOTBOT", budget=60, height_mm=1400, arena=self.ARENA, min_spacing_mm=160
        )
        assert len(one) <= 60 and len(many) <= 60

    def test_an_empty_word_rasterises_to_nothing(self):
        assert (
            len(
                word_points(
                    "", budget=50, height_mm=800, arena=self.ARENA, min_spacing_mm=160
                )
            )
            == 0
        )

    def test_spares_park_on_a_ring_inside_the_walls(self):
        ring = spare_ring(24, self.ARENA, margin=150)
        assert len(ring) == 24
        assert ring[:, 0].min() >= 150 and ring[:, 0].max() <= self.ARENA[0] - 150


class TestGoalsDemo:
    def test_each_bot_joins_the_pin_it_is_nearest(self):
        bots = np.array([[100.0, 100.0], [1900.0, 1900.0], [200.0, 300.0]])
        pins = np.array([[0.0, 0.0], [2000.0, 2000.0]])
        assert split_by_proximity(bots, pins).tolist() == [0, 1, 0]

    def test_a_group_rings_its_pin_with_a_slot_each(self):
        bots = np.array([[900.0, 900.0], [1100.0, 900.0], [1800.0, 1800.0]])
        pins = np.array([[1000.0, 1000.0], [1850.0, 1850.0]])
        targets = ring_targets(bots, pins, 300.0, (2000, 2000))
        assert len(targets) == 3
        # The lone bot of the second group sits on its pin, not on a ring.
        assert np.allclose(targets[2], pins[1])
        for target in targets[:2]:
            assert abs(np.hypot(*(target - pins[0])) - 300.0) < 1.0

    def test_a_ring_that_would_cross_a_wall_is_pulled_inside_it(self):
        bots = np.array([[100.0, 100.0], [200.0, 150.0]])
        pins = np.array([[120.0, 120.0]])
        targets = ring_targets(bots, pins, 400.0, (2000, 2000))
        assert targets[:, 0].min() >= 0 and targets[:, 1].min() >= 0

    def test_no_two_bots_of_a_group_share_a_slot(self):
        rng = np.random.default_rng(5)
        bots = rng.uniform(0, 2000, (30, 2))
        pins = np.array([[500.0, 500.0], [1500.0, 1500.0]])
        targets = ring_targets(bots, pins, 400.0, (2000, 2000))
        assert len({tuple(np.round(t, 3)) for t in targets}) == 30


class TestRegionDemo:
    def test_bots_split_across_regions_by_area(self):
        big = Rect(0, 0, 1000, 1000)
        small = Rect(1200, 0, 500, 500)
        counts = share_by_area([big, small], 100)
        assert sum(counts) == 100
        assert counts[0] > counts[1]

    def test_every_region_gets_a_bot_while_there_are_bots_to_go_round(self):
        rects = [Rect(0, 0, 900, 900), Rect(1000, 0, 100, 100)]
        assert min(share_by_area(rects, 10)) >= 1
        # Fewer bots than regions: the largest regions are the ones filled.
        assert share_by_area(rects, 1) == [1, 0]
        assert share_by_area([], 10) == []

    def test_a_region_is_sampled_into_as_many_points_as_it_gets(self):
        rect = Rect(100, 100, 800, 400)
        for count in (1, 5, 17, 40):
            points = fill_points(rect, count)
            assert len(points) == count
            assert (
                points[:, 0].min() >= rect.x and points[:, 0].max() <= rect.x + rect.w
            )
            assert (
                points[:, 1].min() >= rect.y and points[:, 1].max() <= rect.y + rect.h
            )

    def test_every_bot_gets_its_own_slot_in_the_regions(self):
        rng = np.random.default_rng(2)
        bots = rng.uniform(0, 2000, (25, 2))
        rects = [Rect(0, 0, 800, 800), Rect(1000, 1000, 600, 400)]
        targets = region_targets(bots, rects, (2000, 2000))
        assert len(targets) == 25
        assert len({tuple(np.round(t, 3)) for t in targets}) == 25

    def test_a_region_takes_only_the_bots_it_holds_and_the_rest_park(self):
        small = Rect(0, 0, 500, 500)
        assert capacity(small) == 5
        assert share_by_capacity([small], 100) == [5]
        big = Rect(1000, 0, 2000, 2000)
        counts = share_by_capacity([small, big], 40)
        assert counts[0] <= 5 and sum(counts) == 40
        assert share_by_capacity([small, big], 1000) == [5, 138]
        # A 6 m arena keeps the parking ring clear of the corner rectangle.
        bots = np.random.default_rng(3).uniform(0, 6000, (100, 2))
        targets = region_targets(bots, [small], (6000, 6000))
        inside = ((targets[:, 0] <= 500) & (targets[:, 1] <= 500)).sum()
        assert inside == 5 and len(targets) == 100


class TestShowDemo:
    ARENA = (3000, 3000)

    def test_every_figure_places_one_point_per_bot_inside_the_arena(self):
        for figure in FIGURES:
            for count in (1, 7, 40):
                points = formation(figure, count, self.ARENA, 1.2)
                assert len(points) == count, figure
                assert points[:, 0].min() >= 0 and points[:, 0].max() <= self.ARENA[0]
                assert points[:, 1].min() >= 0 and points[:, 1].max() <= self.ARENA[1]

    def test_the_double_ring_counter_rotates(self):
        early = formation("double ring", 8, self.ARENA, 0.0)
        later = formation("double ring", 8, self.ARENA, 0.4)
        centre = np.array([self.ARENA[0] / 2, self.ARENA[1] / 2])
        angle = lambda p: np.arctan2(*(p - centre)[::-1])  # noqa: E731
        inner = angle(later[0]) - angle(early[0])
        outer = angle(later[4]) - angle(early[4])
        assert inner * outer < 0

    def test_a_still_figure_does_not_move_and_a_moving_one_does(self):
        still = formation("ring", 12, self.ARENA, 0.0)
        assert np.allclose(still, formation("ring", 12, self.ARENA, 0.0))
        assert not np.allclose(still, formation("ring", 12, self.ARENA, 0.5))

    def test_the_hue_follows_the_bearing_from_the_centre(self):
        points = np.array([[2000.0, 1500.0], [1500.0, 2000.0]])
        hues = hue_by_angle(points, self.ARENA)
        assert abs(hues[0] - 0.0) < 1e-6
        assert abs(hues[1] - 90.0) < 1e-6
        assert rgb(0) == (255, 0, 0)

    def test_a_figure_is_drawn_as_a_path_per_ring(self):
        points = formation("double ring", 10, self.ARENA, 0.0)
        assert len(figure_overlay("double ring", points)) == 2
        assert figure_overlay("ring", points)[0]["closed"] is True
        assert "closed" not in figure_overlay("spiral", points)[0]


class TestChargingDemo:
    ARENA = (2000, 2000)

    def test_one_pad_sits_in_each_corner(self):
        places = pads(self.ARENA, inset=300)
        assert len(places) == 4
        assert {(p.x, p.y) for p in places} == {
            (300, 300),
            (1700, 300),
            (300, 1700),
            (1700, 1700),
        }

    def test_a_low_bot_takes_the_nearest_pad_that_is_free(self):
        places = pads(self.ARENA, inset=300)
        bot = Bot(address="AA", x=1800, y=1800, heading=0)
        assert nearest_free(bot, [0, 1, 2, 3], places) == 3
        # With the corner it wants taken, it settles for the next nearest.
        assert nearest_free(bot, [0, 1, 2], places) in (1, 2)
        assert nearest_free(bot, [], places) is None

    def test_a_bot_counts_as_docked_only_inside_the_pad(self):
        pad = Point(300, 300)
        assert docked(Bot("AA", 350, 300, 0), pad)
        assert not docked(Bot("AA", 700, 300, 0), pad)

    def test_a_released_bot_is_left_alone_until_it_has_cleared_the_pad(self):
        cycle = Cycle()
        cycle.holding["AA"] = 0
        cycle.since["AA"] = 100.0
        cycle.release("AA")
        now = time.monotonic()
        assert "AA" not in cycle.holding
        assert cycle.resting("AA", now)
        assert not cycle.resting("AA", now + COOLDOWN_S + 1)
        assert not cycle.resting("BB", now)

    def test_a_pad_a_bot_holds_is_not_offered_to_another(self):
        cycle = Cycle()
        cycle.holding["AA"] = 2
        assert cycle.free_pads(4) == [0, 1, 3]


class TestShippedAnnouncements:
    """Every demo the page will meet, against the schema the page parses."""

    ALL = [FOLLOW, GOALS, REGION, SHOW, LETTERS, CHARGING]
    INPUTS = {"pointer", "goals", "rects", "shapes", "text", "drive"}
    CONTROLS = {"slider", "toggle", "button", "select", "text", "botpicker"}

    def test_each_demo_has_its_own_name_and_topic(self):
        names = [a.name for a in self.ALL]
        assert len(set(names)) == len(names)

    def test_no_demo_declares_an_input_or_control_the_page_cannot_render(self):
        for announcement in self.ALL:
            assert set(announcement.inputs) <= self.INPUTS, announcement.name
            types = {c["type"] for c in announcement.controls}
            assert types <= self.CONTROLS, announcement.name

    def test_control_ids_are_unique_within_a_demo(self):
        for announcement in self.ALL:
            ids = [c["id"] for c in announcement.controls]
            assert len(set(ids)) == len(ids), announcement.name

    def test_every_announcement_is_json_the_page_can_read(self):
        for announcement in self.ALL:
            payload = json.loads(announcement.payload())
            assert payload["name"] == announcement.name
            assert payload["overlay"] is True
            assert payload["ui"] is None

    def test_only_one_demo_claims_each_map_input(self):
        for kind in ("pointer", "goals", "rects", "text"):
            claimants = [a.name for a in self.ALL if kind in a.inputs]
            assert len(claimants) == 1, f"{kind}: {claimants}"


class TestControlValues:
    """Nothing off the broker reaches a loop as a type it did not declare."""

    SPEED = slider("speed", 0, 100, 60)
    FIGURE = select("figure", ["ring", "grid"], "ring")
    WANDER = toggle("wander", True)

    def test_a_slider_is_clamped_to_what_it_declared(self):
        assert coerce_control(self.SPEED, 9999) == 100.0
        assert coerce_control(self.SPEED, -5) == 0.0
        assert coerce_control(self.SPEED, "80") == 80.0

    def test_a_slider_rejects_what_is_not_a_number(self):
        assert coerce_control(self.SPEED, "abc") is None
        assert coerce_control(self.SPEED, None) is None
        assert coerce_control(self.SPEED, float("nan")) is None
        assert coerce_control(self.SPEED, float("inf")) is None

    def test_a_select_only_takes_a_declared_option(self):
        assert coerce_control(self.FIGURE, "grid") == "grid"
        assert coerce_control(self.FIGURE, "spiral") is None
        assert coerce_control(self.FIGURE, 2) is None

    def test_a_toggle_takes_a_bool(self):
        assert coerce_control(self.WANDER, False) is False
        assert coerce_control(self.WANDER, 0) is False
        assert coerce_control(self.WANDER, "nope") is None

    @staticmethod
    def _app():
        app = PlaygroundApp(
            Announcement(
                name="t", title="T", hint="h", controls=[slider("speed", 0, 100, 60)]
            )
        )
        app.swarm = "0000"
        return app

    def _deliver(self, app, message):
        app._on_message(None, None, json.dumps(message).encode(), 0, None)

    def test_a_bad_value_leaves_the_declared_default_standing(self):
        app = self._app()
        self._deliver(app, {"kind": "control", "id": "speed", "value": "abc"})
        assert app.values["speed"] == 60

    def test_an_undeclared_control_never_reaches_the_values(self):
        app = self._app()
        self._deliver(app, {"kind": "control", "id": "whatever", "value": 1})
        assert "whatever" not in app.values

    def test_a_callback_sees_the_coerced_value(self):
        app = self._app()
        seen = []
        app.on_control(seen.append)
        self._deliver(app, {"kind": "control", "id": "speed", "value": 9999})
        assert seen == [ControlChange(client="", id="speed", value=100.0)]

    def test_a_coordinate_that_is_not_finite_is_not_a_coordinate(self):
        assert parse_input(b'{"kind":"goals","points":[{"x":0,"y":NaN}]}') is None
        assert parse_input(b'{"kind":"pointer","at":{"x":Infinity,"y":0}}') is None
        assert (
            parse_input(b'{"kind":"rects","rects":[{"x":0,"y":0,"w":NaN,"h":1}]}')
            is None
        )


class TestReconnect:
    """The demo announces and subscribes on every connect, not only the first."""

    @staticmethod
    def _app():
        app = PlaygroundApp(Announcement(name="t", title="T", hint="h"))
        app.swarm = "0000"
        return app

    def test_connecting_announces_retained_and_subscribes(self):
        app = self._app()
        published, subscribed = [], []

        class FakeClient:
            def publish(self, topic, payload, qos=0, retain=False):
                published.append((topic, payload, qos, retain))

            def subscribe(self, topic, qos=0):
                subscribed.append((topic, qos))

        app._on_connect(FakeClient(), 0, 0, None)
        announce, inbound, _ = app.topics
        assert published == [
            (announce, app.announcement.payload(), 1, True),
        ]
        assert subscribed == [(inbound, 0)]


def _listing_response(bots):
    def handler(request):
        assert request.url.path.endswith("/dotbots")
        return httpx.Response(200, json=bots)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _raw(address, status=0, x=100.0, y=100.0):
    return {
        "address": address,
        "status": status,
        "application": 0,
        "direction": 0,
        "battery": 3.0,
        "lh2_position": {"x": x, "y": y},
    }


class TestFleetBookkeeping:
    @pytest.mark.asyncio
    async def test_a_bot_that_left_the_listing_leaves_the_fleet(self):
        client = ControllerClient()
        client._http = _listing_response([_raw("AA"), _raw("BB")])
        await client.refresh()
        assert set(client.bots) == {"AA", "BB"}

        client._http = _listing_response([_raw("AA")])
        await client.refresh()
        assert set(client.bots) == {"AA"}

    @pytest.mark.asyncio
    async def test_a_lost_bot_does_not_hold_its_slot(self):
        client = ControllerClient()
        client._http = _listing_response([_raw("AA"), _raw("BB")])
        await client.refresh()

        client._http = _listing_response(
            [_raw("AA"), _raw("BB", status=DOTBOT_STATUS_LOST)]
        )
        await client.refresh()
        assert set(client.bots) == {"AA"}

    @pytest.mark.asyncio
    async def test_a_body_that_is_not_json_leaves_the_fleet_as_it_was(self):
        client = ControllerClient()
        client._http = _listing_response([_raw("AA")])
        await client.refresh()

        def handler(request):
            return httpx.Response(502, text="<html>bad gateway</html>")

        client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await client.refresh()
        assert set(client.bots) == {"AA"}


class TestTheFeedStaysUp:
    @pytest.mark.asyncio
    async def test_the_listener_retries_rather_than_dying(self, monkeypatch):
        attempts = []

        def connect(url):
            attempts.append(url)
            raise RuntimeError("boom")

        client = ControllerClient()
        monkeypatch.setattr(
            "dotbot.examples.common.playground.websockets.connect", connect
        )
        task = asyncio.create_task(client._listen())
        await asyncio.sleep(0.05)
        assert not task.done()
        assert attempts
        client._stop.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
