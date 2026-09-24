# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The robots found on one warped camera frame, reported in frame millimetres.

`RobotDetector.detect` runs the two stages - propose, then fit a pose to
each candidate - and classifies each result. Lighthouse fixes, when the
caller has them, name the candidates they stand on. `frame_pose` is the
only place raster pixels and the detector's own heading become the frame
millimetres and the robot `direction` degrees every other surface speaks.

Two heading conventions meet here; `frame_pose` names both and converts.

The pose reported is the BODY orientation of a robot standing still or
moving. The firmware's `direction` is the direction of TRAVEL over the last
stretch of motion. They are different quantities and disagree whenever the
robot slips, turns in place or is pushed.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

import numpy as np

from dotbot.area import Area
from dotbot.camera.detection.pose import (
    NOSE_AHEAD_MM,
    OUTLINE_MM,
    PHOTODIODE_AHEAD_MM,
    WHEELS_MM,
    OutlineFit,
    Template,
    axes,
    component_at,
    features,
    pose_one,
    robot_mask,
    split_region,
)
from dotbot.camera.detection.propose import as_bgr
from dotbot.camera.detection.propose import verify as propose_candidates
from dotbot.robots import robot_geometry

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

# Robots fitted per frame at most, unless the caller sets its own cap.
MAX_ROBOTS = 2

# Wall time one frame may spend fitting poses before the rest wait for the
# next frame. At least one candidate is fitted on every frame, so a slow
# machine still makes progress.
FRAME_BUDGET_MS = 500.0

# How far a lighthouse fix may sit from the outline centre of the robot it
# belongs to: the photodiode's own offset ahead of the centre, the 50 mm the
# firmware holds a fix before replacing it, and the fix's own error.
PRIOR_GATE_MM = robot_geometry().diode_ahead_of_centre_mm + 50.0 + 30.0

# A mask component larger than this, shared by two lighthouse fixes, is two
# robots touching. One robot and its wheels cover about 11000 mm2 on the
# bench camera, and a robot trailing its programming cable about 16000.
SPLIT_MIN_MM2 = 1.5 * robot_geometry().envelope_mm ** 2

# A pose from an earlier frame is re-reported while its robot is still
# proposed, for at most this long.
CARRY_S = 3.0


@dataclass(frozen=True)
class Pose:
    """One fitted pose, in raster pixels and the detector's own degrees."""

    centre_px: tuple[float, float]
    heading_atan2_deg: float
    green_flare: float
    tmpl_margin: float
    refined: bool


@dataclass(frozen=True)
class Prior:
    """Where the lighthouse last put one robot, in raster pixels."""

    address: str
    point_px: tuple[float, float]


@dataclass(frozen=True)
class RobotFix:
    """One robot on one frame: its pose, and whose it is when that is known.

    `stamp` is the time of the frame the pose was fitted on, which is an
    earlier frame's when the budget left this robot for later.
    """

    status: str
    pose: Pose | None
    address: str | None = None
    stamp: float = 0.0


@dataclass(frozen=True)
class Detection:
    """What one frame yielded: one entry per robot fitted.

    Robots carrying an address come first, then the rest, each by the
    strength of its candidate.
    """

    status: str
    candidates: int
    robots: tuple[RobotFix, ...]
    elapsed_ms: float

    @property
    def pose(self) -> Pose | None:
        """The strongest robot's pose, for a caller that expects one robot."""
        return next((r.pose for r in self.robots if r.pose is not None), None)


@dataclass
class _Target:
    """One candidate the frame will report, and what fitting it needs."""

    seed_px: np.ndarray
    z: float
    address: str | None
    key: object = None
    # The seeds of every robot sharing this candidate's mask component, this
    # one's first, when lighthouse fixes say more than one robot stands there.
    split_seeds: list = field(default_factory=list)
    # A robot fitted on another candidate's mask component, which it gives
    # up when that component is too small to hold two robots.
    guest: bool = False


def wrap180(deg: float) -> float:
    """`deg` mapped into (-180, 180]."""
    wrapped = (float(deg) + 180.0) % 360.0 - 180.0
    return 180.0 if wrapped == -180.0 else wrapped


def frame_status(robots) -> str:
    """`found` if any robot was, else `refused` if any was, else `none`."""
    statuses = {r.status for r in robots}
    if FOUND in statuses:
        return FOUND
    if REFUSED in statuses:
        return REFUSED
    return NONE


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
    """The detector one camera runs, holding what outlives one frame.

    `keep_mask` marks the raster pixels that are floor this camera can see:
    the proposer ignores everything outside it and the floor statistics are
    measured inside it. `max_robots` caps the robots reported per frame and
    `budget_ms` the wall time a frame spends fitting them; the ones a frame
    has no time for are fitted first on the next.
    """

    def __init__(
        self,
        mm_per_px: float,
        keep_mask=None,
        exclude_sheets: bool = True,
        max_robots: int = MAX_ROBOTS,
        budget_ms: float = FRAME_BUDGET_MS,
    ):
        self.mm_per_px = float(mm_per_px)
        self.keep_mask = keep_mask
        self.exclude_sheets = bool(exclude_sheets)
        self.max_robots = max(1, int(max_robots))
        self.budget_ms = float(budget_ms)
        self._template = Template(self.mm_per_px)
        self._markers = None
        # Last fit per robot key, as (RobotFix, centre_px).
        self._fits: dict = {}
        self._keys = itertools.count()

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

    def detect(self, bgr, priors=(), stamp: float | None = None) -> Detection:
        """Every verified candidate on this frame, up to the cap, fitted.

        `priors` are the lighthouse fixes of the robots that may stand on
        this raster; a candidate within `PRIOR_GATE_MM` of one carries its
        address. `stamp` is the frame's time, which each fit reports.
        """
        started = time.perf_counter()
        stamp = time.time() if stamp is None else float(stamp)
        bgr = as_bgr(bgr)
        # The evidence maps carry the frame's floor-relative chroma, which is
        # what the colour check reads, so both stages measure one field.
        features_map = features(bgr, self.keep_mask)
        candidates = [
            c
            for c in propose_candidates(
                bgr, self.keep_mask, self.mm_per_px, features_map["chroma"]
            )
            if c["robot"]
        ]
        candidates = _off_sheets(candidates, self.sheet_quads(bgr))
        if not candidates:
            self._fits = {}
            return Detection(NONE, 0, (), _ms_since(started))

        import cv2  # lazy: opencv-python is only required to run the detector

        targets = self._targets(candidates, priors)
        mask = robot_mask(features_map)
        # Whole-frame components, so robots sharing one are seen sharing it
        # even where a fitting window cuts it.
        _, labels = cv2.connectedComponents(mask, connectivity=8)
        fit = OutlineFit(features_map, self.mm_per_px)

        # Oldest fit first, so a budget that cannot cover every robot on one
        # frame covers each of them in turn.
        def age(target):
            held = self._fits.get(target.key)
            return (held[0].stamp if held else -np.inf, -target.z)

        fits = {}
        for target in sorted(targets, key=age):
            if fits and (time.perf_counter() - started) * 1000.0 > self.budget_ms:
                break
            region = self._region(target, targets, mask, labels)
            fits[id(target)] = self._fit(target, region, features_map, fit, stamp)

        robots, kept = [], {}
        for target in targets:
            if id(target) in fits:
                fix = fits[id(target)]
                if fix.pose is None:
                    continue
            else:
                held = self._fits.get(target.key)
                if held is None or stamp - held[0].stamp > CARRY_S:
                    continue
                fix = held[0]
            kept[target.key] = (fix, target.seed_px)
            robots.append(fix)
        self._fits = kept
        return Detection(
            frame_status(robots), len(candidates), tuple(robots), _ms_since(started)
        )

    def _targets(self, candidates, priors) -> list[_Target]:
        """The candidates to report, named where a lighthouse fix allows.

        Pairs are taken nearest first, one fix per candidate. A fix left
        over within reach of a taken candidate means two robots close enough
        to be one blob, so that candidate is fitted once per robot. Named
        candidates are kept before unnamed ones, each by response, up to the
        cap.
        """
        gate = PRIOR_GATE_MM / self.mm_per_px
        targets = [
            _Target(np.asarray(c["centre"], float), float(c["z"]), None)
            for c in candidates
        ]
        points = [np.asarray(p.point_px, float) for p in priors]
        pairs = sorted(
            (float(np.linalg.norm(t.seed_px - q)), ti, pi)
            for ti, t in enumerate(targets)
            for pi, q in enumerate(points)
        )
        taken = match_within(pairs, gate)
        used = set(taken.values())
        for ti, pi in taken.items():
            targets[ti].address = priors[pi].address
        shared = {}
        for dist, ti, pi in pairs:
            if dist > gate:
                break
            if pi in used or ti not in taken:
                continue
            used.add(pi)
            shared.setdefault(ti, [taken[ti]]).append(pi)
        for ti, group in shared.items():
            host = targets[ti]
            for pi in group:
                # Each robot of a shared blob is fitted on its own part, the
                # one grown from its own fix, which is listed first.
                seeds = [points[pi]] + [points[o] for o in group if o != pi]
                if pi == taken[ti]:
                    host.split_seeds = seeds
                else:
                    targets.append(
                        _Target(
                            host.seed_px,
                            host.z,
                            priors[pi].address,
                            split_seeds=seeds,
                            guest=True,
                        )
                    )
        targets.sort(key=lambda t: (t.address is None, -t.z))
        targets = targets[: self.max_robots]
        self._assign_keys(targets)
        return targets

    def _assign_keys(self, targets) -> None:
        """Key each target to the robot it continues from the last frame.

        A named target is keyed by its address; an unnamed one by the
        nearest unnamed fit of the last frame within one robot of it.
        """
        reach = robot_geometry().envelope_mm / self.mm_per_px
        free = {
            key: centre
            for key, (fix, centre) in self._fits.items()
            if fix.address is None
        }
        for target in targets:
            if target.address is not None:
                target.key = ("address", target.address)
                continue
            nearest = min(
                free.items(),
                key=lambda kv: np.linalg.norm(kv[1] - target.seed_px),
                default=None,
            )
            if (
                nearest is not None
                and np.linalg.norm(nearest[1] - target.seed_px) < reach
            ):
                target.key = nearest[0]
                del free[nearest[0]]
            else:
                target.key = ("unnamed", next(self._keys))

    def _region(self, target, targets, mask, labels):
        """The mask pixels `target` is fitted on, or None if there are none.

        Its own component, cut into one part per robot when other robots
        share it: another candidate's seed standing on it, or, for robots
        only the lighthouse tells apart, a component too big for one robot.
        """
        if target.split_seeds:
            region = component_at(
                target.split_seeds[0],
                self.mm_per_px,
                mask,
                win_mm=PRIOR_GATE_MM + robot_geometry().envelope_mm,
                snap_mm=PRIOR_GATE_MM,
            )
            if region is None:
                return None
            if region.sum() * self.mm_per_px**2 < SPLIT_MIN_MM2:
                if target.guest and _label_at(labels, target.seed_px) in labels[region]:
                    return None
                return region
            return split_region(region, target.split_seeds)[0]
        region = component_at(target.seed_px, self.mm_per_px, mask)
        if region is None:
            return None
        h, w = labels.shape
        own = np.bincount(labels[region]).argmax()
        others = [
            other.seed_px
            for other in targets
            if other is not target
            and not other.split_seeds
            and 0 <= int(other.seed_px[1]) < h
            and 0 <= int(other.seed_px[0]) < w
            and labels[int(other.seed_px[1]), int(other.seed_px[0])] == own
        ]
        if not others:
            return region
        # Split the whole component, since the window may have cut the part
        # another robot's seed stands on.
        return split_region(labels == own, [target.seed_px] + others)[0]

    def _fit(self, target, region, features_map, fit, stamp) -> RobotFix:
        """One target's pose, fitted on `region`."""
        fitted = (
            None
            if region is None
            else pose_one(features_map, region, self.mm_per_px, self._template, fit)
        )
        if fitted is None:
            return RobotFix(NONE, None, target.address, stamp)
        pose = Pose(
            centre_px=(float(fitted["centre"][0]), float(fitted["centre"][1])),
            heading_atan2_deg=float(fitted["heading"]),
            green_flare=float(fitted["green_flare"]),
            tmpl_margin=float(fitted["tmpl_margin"]),
            refined=bool(fitted["refined"]),
        )
        return RobotFix(classify(pose), pose, target.address, stamp)


def frame_pose(pose: Pose, area: Area, mm_per_px: float) -> dict:
    """One pose in frame millimetres and both heading conventions.

    Every `*_mm` is frame millimetres, x right and y down, the same frame as
    the area and as an LH2 position. `outline_mm` is the board path and
    `wheels_mm` the two tyre rectangles, both already turned to the heading.

    `heading_atan2_deg` is the detector's own convention: `atan2(dy, dx)` in
    the y-down frame, so 0 = +x and +90 = +y. `heading_deg` is the robot
    `direction` convention the firmware advertises and the console draws:
    0 = +y, +90 = -x (clockwise as drawn with y down), which is
    `heading_atan2_deg - 90` wrapped to (-180, 180].
    """
    origin = np.array([float(area.x), float(area.y)])
    centre = origin + np.asarray(pose.centre_px, float) * mm_per_px
    right, forward = axes(pose.heading_atan2_deg)

    def place(path):
        return [
            _mm(centre + p[0] * right + p[1] * forward) for p in np.asarray(path, float)
        ]

    return {
        "centre_mm": _mm(centre),
        "photodiode_mm": _mm(centre + forward * PHOTODIODE_AHEAD_MM),
        "nose_mm": _mm(centre + forward * NOSE_AHEAD_MM),
        "outline_mm": place(OUTLINE_MM),
        "wheels_mm": [place(wheel) for wheel in WHEELS_MM],
        "heading_deg": round(wrap180(pose.heading_atan2_deg - 90.0), 1),
        "heading_atan2_deg": round(wrap180(pose.heading_atan2_deg), 1),
        "green_flare": round(pose.green_flare, 3),
        "tmpl_margin": round(pose.tmpl_margin, 3),
        "refined": pose.refined,
    }


def _mm(point) -> list[float]:
    """One point as plain floats at a tenth of a millimetre."""
    return [round(float(point[0]), 1), round(float(point[1]), 1)]


def match_within(pairs, gate: float, exact_max: int = 6) -> dict:
    """Candidate to fix, as the most pairs within `gate`, then the least distance.

    `pairs` are `(distance, candidate, fix)` sorted by distance. Candidates
    and fixes linked by pairs within the gate are solved group by group,
    exactly while a group holds at most `exact_max` candidates and nearest
    first above that.
    """
    near = [p for p in pairs if p[0] <= gate]
    parent: dict = {}

    def root(node):
        while parent.setdefault(node, node) != node:
            node = parent[node]
        return node

    for _, ti, pi in near:
        parent[root(("t", ti))] = root(("p", pi))
    groups: dict = {}
    for pair in near:
        groups.setdefault(root(("t", pair[1])), []).append(pair)

    taken: dict = {}
    for group in groups.values():
        candidates = sorted({ti for _, ti, _ in group})
        if len(candidates) > exact_max:
            for _, ti, pi in group:
                if ti not in taken and pi not in taken.values():
                    taken[ti] = pi
            continue
        options = {ti: [(d, pi) for d, t, pi in group if t == ti] for ti in candidates}
        best = (0, 0.0, {})

        def search(k, used, cost, chosen):
            nonlocal best
            if k == len(candidates):
                if (len(chosen), -cost) > (best[0], -best[1]):
                    best = (len(chosen), cost, dict(chosen))
                return
            if len(chosen) + len(candidates) - k < best[0]:
                return
            ti = candidates[k]
            for d, pi in options[ti]:
                if pi not in used:
                    chosen[ti] = pi
                    search(k + 1, used | {pi}, cost + d, chosen)
                    del chosen[ti]
            search(k + 1, used, cost, chosen)

        search(0, frozenset(), 0.0, {})
        taken.update(best[2])
    return taken


def _label_at(labels, point_px) -> int:
    """The component label under `point_px`, clamped onto the raster."""
    h, w = labels.shape
    return int(
        labels[
            min(max(int(point_px[1]), 0), h - 1),
            min(max(int(point_px[0]), 0), w - 1),
        ]
    )


def _ms_since(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 1)
