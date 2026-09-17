# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""One robot found on one warped camera frame, reported in frame millimetres.

`RobotDetector.detect` runs the two stages - propose, then fit a pose - and
classifies the result. `frame_pose` is the only place raster pixels and the
detector's own heading become the frame millimetres and the robot
`direction` degrees every other surface speaks.

THREE HEADING CONVENTIONS MEET HERE, so each is named where it is used:

- `heading_atan2_deg`, the detector's own: `atan2(dy, dx)` in the y-down
  frame, so 0 points along +x and +90 along +y.
- `heading_deg`, the robot `direction` convention the firmware advertises
  and the console draws: 0 points along +y and angles grow clockwise, which
  is `heading_atan2_deg - 90` wrapped to (-180, 180].
- `dotbot.robots.RobotGeometry`, whose offset fields are measured with the
  nose toward the frame's top edge. Nothing here converts to it; it is named
  only so the two are not mistaken for each other.

The pose reported is the BODY orientation of a robot standing still or
moving. The firmware's `direction` is the direction of TRAVEL over the last
stretch of motion. They are different quantities and disagree whenever the
robot slips, turns in place or is pushed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from dotbot.area import Area
from dotbot.detection import propose as _propose
from dotbot.detection.pose import (
    NOSE_AHEAD_MM,
    OUTLINE_MM,
    PHOTODIODE_AHEAD_MM,
    OutlineFit,
    Template,
    axes,
    features,
    pose_at,
    robot_mask,
)

# The two signals that stop the estimator reporting a pose it cannot stand
# behind: how far the green board mass leans toward the nose from the axle,
# and how much better the template scores at the reported heading than at
# that heading turned 180 degrees.
GREEN_LEVER_MIN_MM = 8.0
TMPL_MARGIN_MIN = 0.5

# How far a candidate may sit from the previous pose and still be treated as
# the same robot one warp later. At `WARP_FPS_MAX` that is a tenth of a
# second, in which a DotBot at full speed covers well under this.
WARM_SEED_MAX_MM = 40.0

FOUND = "found"
REFUSED = "refused"
NONE = "none"


@dataclass(frozen=True)
class Pose:
    """One fitted pose, in raster pixels and the detector's own degrees."""

    centre_px: tuple[float, float]
    heading_atan2_deg: float
    green_lever_mm: float
    tmpl_margin: float
    refined: bool


@dataclass(frozen=True)
class Detection:
    """What one frame yielded: a pose, a refused pose, or nothing."""

    status: str
    candidates: int
    pose: Pose | None
    elapsed_ms: float


def wrap180(deg: float) -> float:
    """`deg` mapped into (-180, 180]."""
    wrapped = (float(deg) + 180.0) % 360.0 - 180.0
    return 180.0 if wrapped == -180.0 else wrapped


def classify(pose: Pose) -> str:
    """`found` when both confidence signals clear their floor, else `refused`."""
    if pose.green_lever_mm < GREEN_LEVER_MIN_MM:
        return REFUSED
    if pose.tmpl_margin < TMPL_MARGIN_MIN:
        return REFUSED
    return FOUND


class RobotDetector:
    """The detector one camera runs, holding what is the same every frame.

    `keep_mask` marks the raster pixels that are floor this camera can see:
    the proposer ignores everything outside it and the floor statistics are
    measured inside it.
    """

    def __init__(self, mm_per_px: float, keep_mask=None):
        self.mm_per_px = float(mm_per_px)
        self.keep_mask = keep_mask
        self._template = Template(self.mm_per_px)
        self._last: Pose | None = None

    def detect(self, bgr) -> Detection:
        """The strongest verified candidate on this frame, fitted."""
        started = time.perf_counter()
        candidates = [
            c
            for c in _propose.detect(bgr, self.keep_mask, self.mm_per_px)
            if c["robot"]
        ]
        if not candidates:
            self._last = None
            return Detection(NONE, 0, None, _ms_since(started))
        best = max(candidates, key=lambda c: c["z"])
        features_map = features(bgr, self.keep_mask)
        mask = robot_mask(features_map)
        fit = OutlineFit(features_map, self.mm_per_px)

        fitted = None
        warm = self._warm_seed(best["centre"])
        if warm is not None:
            fitted = self._fit(bgr, best, features_map, mask, fit, warm)
            if not _warm_holds(fitted):
                fitted = None
        if fitted is None:
            fitted = self._fit(bgr, best, features_map, mask, fit, None)

        if fitted is None:
            self._last = None
            return Detection(NONE, len(candidates), None, _ms_since(started))
        pose = Pose(
            centre_px=(float(fitted["centre"][0]), float(fitted["centre"][1])),
            heading_atan2_deg=float(fitted["heading"]),
            green_lever_mm=float(fitted["green_lever_mm"]),
            # A pose fitted without the template check has no margin to
            # stand on, so it is refused rather than passed through.
            tmpl_margin=float(fitted.get("tmpl_margin", 0.0)),
            refined=bool(fitted["refined"]),
        )
        status = classify(pose)
        # Only a pose the estimator stands behind seeds the next frame, so a
        # doubtful answer can never be carried forward as if it were one.
        self._last = pose if status == FOUND else None
        return Detection(status, len(candidates), pose, _ms_since(started))

    def _fit(self, bgr, candidate, features_map, mask, fit, warm):
        return pose_at(
            bgr,
            candidate["centre"],
            self.mm_per_px,
            features_map=features_map,
            mask=mask,
            tmpl=self._template,
            fit=fit,
            warm=warm,
        )

    def _warm_seed(self, centre_px):
        """The previous pose, when this frame's candidate can be the same robot.

        A DotBot cannot cross `WARM_SEED_MAX_MM` of floor between two warps,
        so a candidate further than that is a different robot or the same one
        put down somewhere else, and neither may inherit a heading.
        """
        if self._last is None:
            return None
        moved = (
            float(np.hypot(*(np.asarray(centre_px, float) - self._last.centre_px)))
            * self.mm_per_px
        )
        if moved > WARM_SEED_MAX_MM:
            return None
        return (self._last.centre_px, self._last.heading_atan2_deg)


def _warm_holds(fitted) -> bool:
    """Whether a warm-started fit answered well enough to keep.

    `refined` is the load-bearing one: it is set by measuring the fitted
    pose against this frame's own coarse pose, so a fit that stayed near a
    stale seed fails it no matter how confident the seed was. Anything that
    does not hold is searched again from nothing in the same frame, so a
    robot that was turned or moved costs one extra search and not a wrong
    answer.
    """
    if fitted is None:
        return False
    if not fitted.get("refined"):
        return False
    if fitted.get("tmpl_margin", 0.0) < TMPL_MARGIN_MIN:
        return False
    return fitted.get("green_lever_mm", 0.0) >= GREEN_LEVER_MIN_MM


def frame_pose(pose: Pose, area: Area, mm_per_px: float) -> dict:
    """One pose in frame millimetres and both heading conventions.

    Every `*_mm` is frame millimetres, x right and y down, the same frame as
    the area and as an LH2 position.
    """
    origin = np.array([float(area.x), float(area.y)])
    centre = origin + np.asarray(pose.centre_px, float) * mm_per_px
    right, forward = axes(pose.heading_atan2_deg)
    outline = [
        centre + p[0] * right + p[1] * forward for p in np.asarray(OUTLINE_MM, float)
    ]
    return {
        "centre_mm": _mm(centre),
        "photodiode_mm": _mm(centre + forward * PHOTODIODE_AHEAD_MM),
        "nose_mm": _mm(centre + forward * NOSE_AHEAD_MM),
        "outline_mm": [_mm(p) for p in outline],
        "heading_deg": round(wrap180(pose.heading_atan2_deg - 90.0), 1),
        "heading_atan2_deg": round(wrap180(pose.heading_atan2_deg), 1),
        "green_lever_mm": round(pose.green_lever_mm, 1),
        "tmpl_margin": round(pose.tmpl_margin, 3),
        "refined": pose.refined,
    }


def _mm(point) -> list[float]:
    """One point as plain floats at a tenth of a millimetre."""
    return [round(float(point[0]), 1), round(float(point[1]), 1)]


def _ms_since(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 1)
