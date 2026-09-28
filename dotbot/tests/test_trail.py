"""Tests for the trail store."""

from dotbot.models import DotBotGPSPosition, DotBotLH2Position
from dotbot.trail import Trail


def _filled(count, maxlen=4):
    trail = Trail(maxlen)
    evicted = [trail.append(i, DotBotLH2Position(x=i, y=-i)) for i in range(count)]
    return trail, evicted


def test_trail_keeps_the_newest_points_and_names_the_evicted_seq():
    trail, evicted = _filled(6)
    assert evicted == [None, None, None, None, 0, 1]
    assert len(trail) == 4
    assert [p["x"] for p in trail.json()] == [2, 3, 4, 5]
    assert trail.last() == DotBotLH2Position(x=5, y=-5)


def test_trail_json_filters_by_count_and_seq():
    trail, _ = _filled(7)
    assert trail.json() == [{"x": float(i), "y": float(-i)} for i in range(3, 7)]
    assert [p["x"] for p in trail.json(2)] == [5, 6]
    assert [p["x"] for p in trail.json(2, upto=4)] == [3, 4]
    assert [p["x"] for p in trail.json(after=4)] == [5, 6]
    assert [p["x"] for p in trail.json(1, after=4)] == [6]
    assert trail.json(0) == []


def test_trail_clear_and_gps_points():
    trail, _ = _filled(6)
    trail.clear()
    assert len(trail) == 0 and trail.last() is None and trail.json() == []
    trail.append(9, DotBotGPSPosition(latitude=48.8, longitude=2.3))
    assert trail.json() == [{"latitude": 48.8, "longitude": 2.3}]
    assert trail.last() == DotBotGPSPosition(latitude=48.8, longitude=2.3)
