# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Finding the camera that sees the sheets, and reading them back.

Everything that touches a video source: opening one, letting it settle,
probing the indices to find which one is over the area, and reading the
sheets `--reads` times. Nothing here knows about the homography.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from dotbot.camera.sheets import MARKER_DICTIONARY, layout_ids

# An OpenCV index is assigned per machine and per session, so no file and no
# flag default can carry it: `collect` opens the indices in turn and keeps
# the one that sees the sheets.
PROBE_INDEX_MAX = 10
PROBE_MISSES_MAX = 2

# Two of three cameras on the bench return a black first frame and a live
# second, and ArUco on black reports zero markers - which reads as "no
# sheets" when the truth is "not ready". Frames are read until one is lit,
# or until the budget runs out.
LIT_MEAN_MIN = 8.0
SETTLE_FRAMES_MAX = 10
SETTLE_SECONDS_MAX = 2.0

# What disqualifies a source when nothing sees markers: a lens cap or a dark
# room, and a blank wall or a ceiling. Telling a floor from a face is not
# attempted - both are lit and structured, and a rule ranking them would be
# a guess dressed as a measurement.
DARK_MEAN_MAX = 20.0
FLAT_SPREAD_MAX = 12.0

READS_DEFAULT = 25


def open_capture(source: int | str, open_source: Callable | None = None):
    """Open one video source, defaulting to `cv2.VideoCapture`.

    Every read of a camera goes through here, and `open_source` is the seam
    a scripted capture is handed in on, so the probe, the choice and the
    reads are all exercisable without a device.
    """
    if open_source is not None:
        return open_source(source)
    import cv2  # lazy: opencv-python is only required to read a camera

    return cv2.VideoCapture(source)


def _gray(frame: np.ndarray | None) -> np.ndarray | None:
    """One frame as single-channel luminance, whatever the source delivers."""
    if frame is None:
        return None
    frame = np.asarray(frame)
    if frame.ndim == 2:
        return frame
    import cv2

    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def build_detector(dictionary: str = MARKER_DICTIONARY):
    """The detector every read runs through, with sub-pixel refinement.

    Refinement is what takes a corner from the nearest whole pixel to a
    fraction of one, and at about 1 mm of floor per pixel it is the
    difference between a millimetre registration and a pixel one.
    """
    import cv2

    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary)),
        parameters,
    )


def detect_markers(frame: np.ndarray, detector) -> dict[int, np.ndarray]:
    """Every marker in one frame, as id to its four pixel corners.

    An id the detector returns more than once is dropped rather than
    arbitrated: two candidates decoding to one id means one of them is not
    the sheet, and nothing in the image says which.
    """
    corners, ids, _ = detector.detectMarkers(_gray(frame))
    if ids is None:
        return {}
    found: dict[int, np.ndarray] = {}
    seen: set[int] = set()
    for marker_id, quad in zip((int(i) for i in ids.ravel()), corners):
        if marker_id in seen:
            found.pop(marker_id, None)
            continue
        seen.add(marker_id)
        found[marker_id] = np.asarray(quad, dtype=np.float64).reshape(4, 2)
    return found


def duplicate_ids(frame: np.ndarray, detector) -> tuple[int, ...]:
    """The ids this frame decoded more than once."""
    _, ids, _ = detector.detectMarkers(_gray(frame))
    if ids is None:
        return ()
    flat = [int(i) for i in ids.ravel()]
    return tuple(sorted({i for i in flat if flat.count(i) > 1}))


@dataclass
class Settled:
    """The first lit frame a source delivered, and what was thrown away."""

    frame: np.ndarray | None = None
    discarded: int = 0
    lit: bool = False


def settle(capture, frames_max: int = SETTLE_FRAMES_MAX) -> Settled:
    """Read until a frame has an image in it, or the budget runs out.

    Returns the first lit frame, or the last one read when none was lit, so
    a caller always has something to show for a source that delivered
    anything at all.
    """
    import time

    deadline = time.monotonic() + SETTLE_SECONDS_MAX
    last: np.ndarray | None = None
    discarded = 0
    for _ in range(frames_max):
        ok, frame = capture.read()
        if not ok or frame is None:
            break
        gray = _gray(frame)
        if float(np.mean(gray)) >= LIT_MEAN_MIN:
            return Settled(frame=frame, discarded=discarded, lit=True)
        last = frame
        discarded += 1
        if time.monotonic() >= deadline:
            break
    return Settled(frame=last, discarded=max(discarded - 1, 0), lit=False)


@dataclass
class Probe:
    """What one video source looks like, and whether it sees the sheets."""

    source: int | str
    opened: bool = False
    backend: str = ""
    width: int = 0
    height: int = 0
    fps: float = 0.0
    discarded: int = 0
    mean: float = 0.0
    spread: float = 0.0
    marker_ids: tuple[int, ...] = ()
    frame: np.ndarray | None = None
    note: str = ""

    @property
    def dark(self) -> bool:
        """A lens cap or an unlit room."""
        return self.mean < DARK_MEAN_MAX

    @property
    def flat(self) -> bool:
        """A blank wall or a ceiling: lit, but with nothing in it."""
        return self.spread < FLAT_SPREAD_MAX

    @property
    def scene(self) -> bool:
        """Something is in front of this camera."""
        return self.frame is not None and not self.dark and not self.flat

    @property
    def row(self) -> str:
        """The source's line in the table printed before the reads."""
        head = f"{str(self.source):<4}"
        if not self.opened:
            return f"{head}  did not open"
        if self.frame is None:
            return f"{head}  {self.backend:<12}  no frames"
        markers = " ".join(str(i) for i in self.marker_ids) or "none"
        tail = ""
        if not self.marker_ids and self.dark:
            tail = "  (dark)"
        elif not self.marker_ids and self.flat:
            tail = "  (flat)"
        return (
            f"{head}  {self.backend:<12}  {self.width} x {self.height:<5}  "
            f"{self.fps:g} fps  discarded {self.discarded}  "
            f"mean {self.mean:<5.0f} spread {self.spread:<4.0f} "
            f"markers {markers}{tail}"
        )


def probe(
    source: int | str,
    open_source: Callable | None = None,
    detector=None,
) -> Probe:
    """Open one source, settle it, and report what it sees."""
    capture = open_capture(source, open_source)
    if not capture.isOpened():
        release_capture(capture)
        return Probe(source=source, note="did not open")
    try:
        settled = settle(capture)
        backend = str(getattr(capture, "getBackendName", lambda: "")() or "")
        fps = float(capture_fps(capture))
    finally:
        release_capture(capture)
    if settled.frame is None:
        return Probe(source=source, opened=True, backend=backend, note="no frames")
    gray = _gray(settled.frame)
    height, width = gray.shape[:2]
    found = detect_markers(settled.frame, detector or build_detector())
    return Probe(
        source=source,
        opened=True,
        backend=backend,
        width=int(width),
        height=int(height),
        fps=fps,
        discarded=settled.discarded,
        mean=float(np.mean(gray)),
        spread=float(np.std(gray)),
        marker_ids=tuple(sorted(found)),
        frame=settled.frame,
    )


def capture_fps(capture) -> float:
    """The frame rate the source declares, or zero when it declares none."""
    import cv2

    try:
        return float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    except Exception:  # noqa: BLE001 - a scripted or exotic source may not
        return 0.0


def release_capture(capture) -> None:
    """Hand the device back, for a capture that has one to hand back."""
    release = getattr(capture, "release", None)
    if release is not None:
        release()


def discover(
    open_source: Callable | None = None,
    detector=None,
    index_max: int = PROBE_INDEX_MAX,
) -> list[Probe]:
    """Probe the OpenCV indices in turn, in the order they are numbered.

    Stops after `PROBE_MISSES_MAX` consecutive indices fail to open, since
    the numbering is dense from zero on every backend seen so far, and at
    `index_max` in any case.
    """
    detector = detector or build_detector()
    probes: list[Probe] = []
    misses = 0
    for index in range(index_max):
        found = probe(index, open_source, detector)
        if not found.opened:
            misses += 1
            if misses >= PROBE_MISSES_MAX:
                probes.append(found)
                break
            probes.append(found)
            continue
        misses = 0
        probes.append(found)
    return probes


@dataclass
class Choice:
    """Which source `collect` will read, or why it will not choose one."""

    probe: Probe | None = None
    reason: str = ""
    missing: tuple[int, ...] = ()

    @property
    def chosen(self) -> bool:
        return self.probe is not None


def choose(probes: Sequence[Probe], ids: Sequence[int] | None = None) -> Choice:
    """The source that sees the sheets, in the order of 2.8's rules.

    Markers decide when exactly one source sees any; a subset of the layout
    is named and accepted, since the reads will show whether it was the
    warm-up or the placement. With no markers anywhere, one lit scene is
    chosen and the operator confirms it from its probe frame - the case
    before any sheet exists. Anything else refuses to guess.
    """
    ids = tuple(ids if ids is not None else layout_ids())
    seeing = [p for p in probes if p.marker_ids]
    if len(seeing) == 1:
        found = seeing[0]
        missing = tuple(i for i in ids if i not in found.marker_ids)
        sheets = " ".join(str(i) for i in found.marker_ids)
        reason = f"source {found.source} sees sheets {sheets}: chosen"
        if missing:
            reason += f"; missing {' '.join(str(i) for i in missing)}"
        return Choice(probe=found, reason=reason, missing=missing)
    if len(seeing) > 1:
        sources = ", ".join(str(p.source) for p in seeing)
        return Choice(
            reason=(
                f"sources {sources} all see markers of this dictionary, and "
                "only you know which one is over the area"
            )
        )

    scenes = [p for p in probes if p.scene]
    if len(scenes) == 1:
        found = scenes[0]
        return Choice(
            probe=found,
            reason=f"source {found.source} sees no markers; the one lit scene",
            missing=ids,
        )
    if len(scenes) > 1:
        sources = ", ".join(str(p.source) for p in scenes)
        return Choice(
            reason=(
                f"no source sees markers, and sources {sources} all show a lit "
                "scene; check their probe frames"
            )
        )
    opened = [str(p.source) for p in probes if p.opened]
    listed = ", ".join(opened) if opened else "none"
    return Choice(reason=f"no source shows a lit scene (opened: {listed})")


def annotate(frame: np.ndarray, found: dict[int, np.ndarray]) -> np.ndarray:
    """One frame with the markers it decoded drawn on it, in colour."""
    import cv2

    frame = np.asarray(frame)
    canvas = (
        cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame.copy()
    )
    if not found:
        return canvas
    ids = np.array([[i] for i in sorted(found)], dtype=np.int32)
    corners = [found[i].reshape(1, 4, 2).astype(np.float32) for i in sorted(found)]
    cv2.aruco.drawDetectedMarkers(canvas, corners, ids)
    return canvas


def write_annotated(
    frame: np.ndarray, found: dict[int, np.ndarray], path: Path
) -> Path:
    """One frame with its detections drawn, as a `.jpg` beside the file."""
    import cv2

    cv2.imwrite(str(path), annotate(frame, found))
    return path


def write_probe_frames(probes: Sequence[Probe], directory: Path) -> list[Path]:
    """One annotated `.jpg` per source that delivered a frame."""
    directory.mkdir(parents=True, exist_ok=True)
    detector = build_detector()
    written = []
    for found in probes:
        if found.frame is None:
            continue
        path = directory / f"source-{_source_slug(found.source)}.jpg"
        written.append(
            write_annotated(found.frame, detect_markers(found.frame, detector), path)
        )
    return written


def _source_slug(source: int | str) -> str:
    """A source as a filename fragment: an index as itself, a path as its stem."""
    if isinstance(source, int):
        return str(source)
    return _slug(Path(str(source)).stem) or "path"


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "-" for c in text).strip("-.")


def parse_source(text: str) -> int | str:
    """What `--camera` names: an OpenCV index, or a path to open directly."""
    stripped = text.strip()
    if stripped.isdigit():
        return int(stripped)
    return stripped


@dataclass
class ReadTally:
    """What `--reads` reads of the sheets actually yielded.

    A black read is counted apart from a read that saw no markers: the two
    have different causes and only one of them means the sheets are not
    down.
    """

    target: int = 0
    complete: int = 0
    black: int = 0
    duplicated: int = 0
    short: int = 0
    stopped: int = 0
    discarded: int = 0
    missing: tuple[int, ...] = ()
    extra: tuple[int, ...] = ()

    @property
    def summary(self) -> str:
        """The one line printed when the reads are done."""
        markers = len(layout_ids()) if self.complete else 0
        line = f"{markers} markers in {self.complete} of {self.target} reads"
        notes = []
        if self.black:
            notes.append(f"black {self.black}")
        if self.duplicated:
            notes.append(f"duplicate ids {self.duplicated}")
        if self.short:
            notes.append(f"incomplete {self.short}")
        if self.stopped:
            notes.append(f"no frame {self.stopped}")
        if notes:
            line += " (" + ", ".join(notes) + ")"
        return line


def capture_reads(
    capture,
    ids: Sequence[int],
    reads: int,
    detector=None,
) -> tuple[list[dict[int, np.ndarray]], ReadTally, np.ndarray | None]:
    """Read the sheets `reads` times, keeping the reads that saw all of them.

    The warm-up runs first and its settled frame is the first read, which is
    what lets a single recorded frame stand in for a camera. Returns the
    kept reads, the tally, and the last frame seen so the operator has a
    picture of what was registered.
    """
    detector = detector or build_detector()
    ids = tuple(ids)
    tally = ReadTally(target=reads)
    kept: list[dict[int, np.ndarray]] = []
    missing: set[int] = set()
    extra: set[int] = set()
    last: np.ndarray | None = None

    settled = settle(capture)
    tally.discarded = settled.discarded
    frame = settled.frame
    for _ in range(reads):
        if frame is None:
            tally.stopped += 1
            ok, frame = capture.read()
            if not ok or frame is None:
                frame = None
                continue
        last = frame
        gray = _gray(frame)
        if float(np.mean(gray)) < LIT_MEAN_MIN:
            tally.black += 1
        else:
            duplicates = duplicate_ids(frame, detector)
            found = detect_markers(frame, detector)
            extra.update(i for i in found if i not in ids)
            wanted = {i: found[i] for i in ids if i in found}
            if duplicates:
                tally.duplicated += 1
            elif len(wanted) == len(ids):
                kept.append(wanted)
            else:
                tally.short += 1
                missing.update(i for i in ids if i not in wanted)
        ok, frame = capture.read()
        if not ok or frame is None:
            frame = None

    tally.complete = len(kept)
    tally.missing = tuple(sorted(missing))
    tally.extra = tuple(sorted(extra))
    return kept, tally, last


def average_corners(
    reads: Sequence[dict[int, np.ndarray]], ids: Sequence[int]
) -> dict[int, np.ndarray]:
    """The sixteen pixel corners, averaged over every complete read."""
    if not reads:
        raise ValueError("no read saw every marker, so there is nothing to average")
    return {
        marker_id: np.mean([read[marker_id] for read in reads], axis=0)
        for marker_id in ids
    }
