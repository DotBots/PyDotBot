"""Tests for the camera detector's rate, run on a clock the test advances."""

import pytest

from dotbot.camera.rate import DetectRate


class Clock:
    def __init__(self):
        self.now = 0.0


def run(rate, clock, cost_s, frames):
    """`frames` detections of `cost_s` each, started as soon as each is due.

    Returns the share of the elapsed time spent detecting.
    """
    started_at = clock.now
    busy = 0.0
    for _ in range(frames):
        clock.now += rate.wait_s(clock.now)
        rate.ran(clock.now, cost_s)
        clock.now += cost_s
        busy += cost_s
    clock.now += rate.wait_s(clock.now)
    return busy / (clock.now - started_at)


def test_a_cheap_detector_runs_at_the_warp_rate():
    rate, clock = DetectRate(0.4, max_hz=10.0), Clock()
    run(rate, clock, 0.01, 20)
    assert rate.hz == pytest.approx(10.0)


@pytest.mark.parametrize("cost_s", [0.12, 0.25, 0.6])
def test_an_expensive_detector_holds_its_share_of_a_core(cost_s):
    rate, clock = DetectRate(0.4, max_hz=10.0), Clock()
    run(rate, clock, cost_s, 10)
    assert run(rate, clock, cost_s, 20) == pytest.approx(0.4, abs=0.01)
    assert rate.hz == pytest.approx(0.4 / cost_s, rel=0.01)


def test_the_rate_falls_as_robots_are_added_and_recovers_when_they_leave():
    rate, clock = DetectRate(0.4, max_hz=10.0), Clock()
    run(rate, clock, 0.15, 20)
    one = rate.hz
    run(rate, clock, 0.6, 20)
    five = rate.hz
    run(rate, clock, 0.15, 20)
    assert five < one / 3
    assert rate.hz == pytest.approx(one, rel=0.01)


def test_the_rate_never_falls_below_its_floor():
    rate, clock = DetectRate(0.4, max_hz=10.0, min_hz=0.5), Clock()
    run(rate, clock, 5.0, 5)
    assert rate.hz == pytest.approx(0.5)
    assert rate.wait_s(clock.now) == 0.0


def test_one_slow_frame_moves_the_rate_by_a_fraction_of_its_cost():
    rate, clock = DetectRate(0.4, max_hz=10.0, smoothing=0.3), Clock()
    run(rate, clock, 0.2, 20)
    rate.ran(clock.now, 2.0)
    assert rate.cost_s == pytest.approx(0.2 + 0.3 * 1.8)


def test_a_change_is_reported_once_per_step_not_per_frame():
    rate, clock = DetectRate(0.4, max_hz=10.0), Clock()
    reports = []
    for cost_s in [0.2] * 10 + [0.6] * 10:
        clock.now += rate.wait_s(clock.now)
        reports.append(rate.ran(clock.now, cost_s))
        clock.now += cost_s
    assert reports[0]
    assert not any(reports[1:10])
    # The average climbs over a few frames, so the step is reported in a
    # few moves rather than one, and then goes quiet.
    assert 1 <= sum(reports[10:]) <= 4
    assert not any(reports[16:])


def test_a_share_outside_one_core_is_refused():
    with pytest.raises(ValueError):
        DetectRate(0.0)
    with pytest.raises(ValueError):
        DetectRate(1.5)
