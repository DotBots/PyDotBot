"""The playground contract: announcement, will, input parsing, coalescing."""

import json
import random

from dotbot.examples.common.playground import (
    Announcement,
    CommandQueue,
    ControlChange,
    Point,
    PointerSample,
    app_topics,
    clear_message,
    parse_input,
    slider,
    toggle,
)
from dotbot.examples.follow.follow import (
    ANNOUNCEMENT,
    follow_target,
    separation,
    wander_target,
)


class TestAnnouncement:
    def test_payload_carries_every_field_the_page_renders(self):
        payload = json.loads(ANNOUNCEMENT.payload())
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
        assert ANNOUNCEMENT.defaults() == {"speed": 60, "spread": 2, "wander": True}
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
        message = {"kind": "goals", "client": "c1", "points": [{"x": 1, "y": 2}]}
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
