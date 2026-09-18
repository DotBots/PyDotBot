# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""One robot found on one warped camera frame, reported in frame millimetres.

`RobotDetector.detect` runs the two stages - propose, then fit a pose - and
classifies the result. `frame_pose` is the only place raster pixels and the
detector's own heading become the frame millimetres and the robot
`direction` degrees every other surface speaks.

TWO HEADING CONVENTIONS MEET HERE, so each is named where it is used:

- `heading_atan2_deg`, the detector's own: `atan2(dy, dx)` in the y-down
  frame, so 0 = +x and +90 = +y.
- `heading_deg`, the robot `direction` convention the firmware advertises
  and the console draws: 0 = +y, +90 = -x (clockwise as drawn with y down),
  which is `heading_atan2_deg - 90` wrapped to (-180, 180].

`dotbot.robots.RobotGeometry` carries no heading; only its scalar offsets
are read.

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
from dotbot.camera.detection.pose import (
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
from dotbot.camera.detection.propose import verify as propose_candidates

# The two signals that stop the estimator reporting a pose it cannot stand
# behind: the share of the wide green mass lying toward the nose, and how much
# better the template scores at the reported heading than at that heading
# turned 180 degrees. A robot the right way round scores about 0.8 and one
# turned around scores its negative, so this floor is a long way from both.
GREEN_FLARE_MIN = 0.15
TMPL_MARGIN_MIN = 0.5

# A registration sheet is white paper, which the colour check reads as floor
# whenever the page and the floor sit under the same light. What it cannot
# read as floor is a page carrying ink, a gloss highlight or a cast the floor
# does not share, so a sheet can still propose a candidate and be fitted into
# a pose, and a sheet's candidate can win. The sheets are found frame by frame
# from the markers that make them sheets, never remembered from the
# registration, so lifting them stops the exclusion on the next frame and no
# floor is given up for the rest of the run. Grown about its centre, the
# marker quad covers the page it is printed on.
SHEET_GROW = 1.4

FOUND = "found"
REFUSED = "refused"
NONE = "none"


@dataclass(frozen=True)
class Pose:
    """One fitted pose, in raster pixels and the detector's own degrees."""

    centre_px: tuple[float, float]
    heading_atan2_deg: float
    green_flare: float
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
    if pose.green_flare < GREEN_FLARE_MIN:
        return REFUSED
    if pose.tmpl_margin < TMPL_MARGIN_MIN:
        return REFUSED
    return FOUND


def _off_sheets(candidates, quads):
    """The candidates whose centre is not standing on one of `quads`.

    Only the centre is tested, so a robot parked against a sheet is still
    proposed. Cutting the pages out of the keep mask instead would take a
    robot's width of floor with each of them, since a candidate needs its
    whole footprint on known floor.
    """
    if not quads:
        return candidates
    import cv2  # lazy: opencv-python is only required to run the detector

    kept = []
    for candidate in candidates:
        point = (float(candidate["centre"][0]), float(candidate["centre"][1]))
        if any(cv2.pointPolygonTest(quad, point, False) >= 0 for quad in quads):
            continue
        kept.append(candidate)
    return kept


class RobotDetector:
    """The detector one camera runs, holding what is the same every frame.

    `keep_mask` marks the raster pixels that are floor this camera can see:
    the proposer ignores everything outside it and the floor statistics are
    measured inside it.
    """

    def __init__(self, mm_per_px: float, keep_mask=None, exclude_sheets: bool = True):
        self.mm_per_px = float(mm_per_px)
        self.keep_mask = keep_mask
        self.exclude_sheets = bool(exclude_sheets)
        self._template = Template(self.mm_per_px)
        self._markers = None

    def sheet_quads(self, bgr) -> list:
        """The registration pages in this frame, as raster-pixel polygons.

        Each marker quad grown by `SHEET_GROW` about its own centre, which
        is what reaches past the marker to the paper around it.
        """
        if not self.exclude_sheets:
            return []
        # lazy: importing the capture module pulls in the ArUco detector, and
        # a detector built per frame costs more than the search it runs.
        from dotbot.camera.capture import build_detector, detect_markers

        if self._markers is None:
            self._markers = build_detector()
        quads = []
        for quad in detect_markers(bgr, self._markers).values():
            quad = np.asarray(quad, dtype=np.float32)
            centre = quad.mean(axis=0)
            quads.append(centre + (quad - centre) * SHEET_GROW)
        return quads

    def detect(self, bgr) -> Detection:
        """The strongest verified candidate on this frame, fitted."""
        started = time.perf_counter()
        # The evidence maps carry the frame's floor-relative chroma, which is
        # what the colour check reads, so both stages measure one field.
        features_map = features(bgr, self.keep_mask)
        candidates = [
            c
            for c in propose_candidates(
                bgr, self.keep_mask, self.mm_per_px, chroma=features_map["chroma"]
            )
            if c["robot"]
        ]
        candidates = _off_sheets(candidates, self.sheet_quads(bgr))
        if not candidates:
            return Detection(NONE, 0, None, _ms_since(started))
        best = max(candidates, key=lambda c: c["z"])
        mask = robot_mask(features_map)
        fitted = pose_at(
            bgr,
            best["centre"],
            self.mm_per_px,
            features_map=features_map,
            mask=mask,
            tmpl=self._template,
            fit=OutlineFit(features_map, self.mm_per_px),
        )
        if fitted is None:
            return Detection(NONE, len(candidates), None, _ms_since(started))
        pose = Pose(
            centre_px=(float(fitted["centre"][0]), float(fitted["centre"][1])),
            heading_atan2_deg=float(fitted["heading"]),
            green_flare=float(fitted["green_flare"]),
            # A pose fitted without the template check has no margin to
            # stand on, so it is refused rather than passed through.
            tmpl_margin=float(fitted.get("tmpl_margin", 0.0)),
            refined=bool(fitted["refined"]),
        )
        return Detection(classify(pose), len(candidates), pose, _ms_since(started))


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
        "green_flare": round(pose.green_flare, 3),
        "tmpl_margin": round(pose.tmpl_margin, 3),
        "refined": pose.refined,
    }


def _mm(point) -> list[float]:
    """One point as plain floats at a tenth of a millimetre."""
    return [round(float(point[0]), 1), round(float(point[1]), 1)]


def _ms_since(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 1)
