# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""How often a camera's detector runs: often enough, and never more than its share.

The detector's cost grows with the robots in view and with whatever else
the machine is doing, so the interval between detections is chosen from
what they have been taking: a running average of the wall time per
detection, divided by the share of one core the detector may hold. More
robots or a busier machine lower the rate, and it recovers when either
goes away. It never rises above the warp rate, since there would be no new
frame to detect on, and never falls below `DETECT_HZ_MIN`.
"""

from __future__ import annotations

# The share of one core detection may hold, on average.
DETECT_SHARE = 0.4

# Slowest rate the controller will go to, whatever a detection costs.
DETECT_HZ_MIN = 0.5

# Weight of the newest detection in the running average of the cost.
SMOOTHING = 0.3

# A rate is reported as changed once it moves this far from the last one
# reported, as a fraction of it, so the log carries steps and not jitter.
REPORT_STEP = 0.25


class DetectRate:
    """The interval between detection starts that holds them to `share`.

    Times are seconds on whatever clock the caller reads; nothing here
    reads one.
    """

    def __init__(
        self,
        share: float = DETECT_SHARE,
        max_hz: float = 10.0,
        min_hz: float = DETECT_HZ_MIN,
        smoothing: float = SMOOTHING,
    ):
        if not 0.0 < share <= 1.0:
            raise ValueError(f"detection share must be in (0, 1], got {share}")
        self.share = float(share)
        self.max_hz = float(max_hz)
        self.min_hz = min(float(min_hz), self.max_hz)
        self.smoothing = float(smoothing)
        self.cost_s: float | None = None
        self._next = 0.0
        self._reported_hz: float | None = None

    @property
    def interval_s(self) -> float:
        """Seconds from one detection's start to the next one's."""
        if self.cost_s is None:
            return 1.0 / self.max_hz
        interval = self.cost_s / self.share
        return min(max(interval, 1.0 / self.max_hz), 1.0 / self.min_hz)

    @property
    def hz(self) -> float:
        return 1.0 / self.interval_s

    def wait_s(self, now: float) -> float:
        """How long until the next detection is due, zero if it is."""
        return max(0.0, self._next - now)

    def ran(self, started: float, seconds: float) -> bool:
        """Record one detection; True when the rate moved by `REPORT_STEP`."""
        seconds = max(0.0, float(seconds))
        if self.cost_s is None:
            self.cost_s = seconds
        else:
            self.cost_s += self.smoothing * (seconds - self.cost_s)
        self._next = started + self.interval_s
        hz = self.hz
        if (
            self._reported_hz is None
            or abs(hz - self._reported_hz) > REPORT_STEP * self._reported_hz
        ):
            self._reported_hz = hz
            return True
        return False
