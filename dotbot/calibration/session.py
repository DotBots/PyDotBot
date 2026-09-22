# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""One capture session: the points, which is outstanding, and what was stored.

The capture is a stateful loop with one point outstanding at a time, and
whichever robot answers it is that point. This module holds that loop as an
object so the CLI prompt and the console's calibration mode drive one
implementation rather than two: same resolver, same capture-quality guard,
same solver and same writer, so a file saved from either is byte-identical
for the same reads.

Nothing here talks to a transport. The caller hands in a `PointCapture`, or
a swarmit `CaptureSession` to take one with.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from dotbot.calibration.lighthouse2 import (
    VALID_MM_DEFAULT,
    Calibration,
    LighthouseManager,
    Placement,
    StationSolution,
    calibration_payload,
    read_calibration_file,
)
from dotbot.calibration.ota import (
    CAPTURE_READS_DEFAULT,
    CAPTURE_RETRIES_DEFAULT,
    CAPTURE_TIMEOUT_DEFAULT,
    PointCapture,
    samples_from_reads,
)
from dotbot.calibration.points import (
    PointPlacement,
    resolve_placement_points,
)
from dotbot.robots import ROBOT_DEFAULT
from dotbot.site import Site

# A homography has eight unknowns, so four points fix it exactly.
POINTS_MIN = 4


class SessionError(Exception):
    """A session asked to do something its state does not allow."""


@dataclass
class SessionPoint:
    """One resolved point of the session, and what has been captured at it."""

    index: int
    placement: PointPlacement
    capture: PointCapture | None = None
    # Reads received per station while this point's capture is running.
    reads_per_station: dict[int, int] = field(default_factory=dict)
    reads_target: int = 0

    @property
    def captured(self) -> bool:
        return self.capture is not None

    @property
    def mm(self) -> tuple[float, float]:
        return self.placement.mm


@dataclass
class CalibrationSession:
    """The points of one placement, captured in order, then solved and saved."""

    points: list[SessionPoint]
    site: Site
    at: str = ""
    # The area the expected error will be evaluated over; "" means none.
    area: str = ""
    device: str = ""
    robot: str = ROBOT_DEFAULT
    reads: int = CAPTURE_READS_DEFAULT
    timeout: float = CAPTURE_TIMEOUT_DEFAULT
    retries: int = CAPTURE_RETRIES_DEFAULT
    tag: str = ""
    stations: list[StationSolution] = field(default_factory=list)
    unsolved: list[tuple[int, int]] = field(default_factory=list)
    saved_path: str | None = None
    saved_id: str = ""
    saved: Calibration | None = None
    # The predictor of the plan's accuracy section is a later phase, so the
    # number is absent rather than guessed, and a renderer shows the line
    # only when it is one.
    expected_error_mm: float | None = None
    error: str = ""

    @classmethod
    def resolve(
        cls,
        specs: Sequence[str],
        site: Site | None = None,
        robot: str = ROBOT_DEFAULT,
        **kwargs: Any,
    ) -> CalibrationSession:
        """A session over the points one `--points` specification stands for."""
        site = site or Site()
        placements = resolve_placement_points(specs, site.registry(), robot)
        if len(placements) < POINTS_MIN:
            raise SessionError(
                f"a homography needs at least {POINTS_MIN} points, the points "
                f"given resolved to {len(placements)}. Span the area you will "
                f"drive in."
            )
        return cls(
            points=[
                SessionPoint(index=i, placement=p) for i, p in enumerate(placements)
            ],
            site=site,
            at=" ".join(specs),
            robot=robot,
            **kwargs,
        )

    # -- where the loop is

    @property
    def outstanding(self) -> SessionPoint | None:
        """The point waiting to be captured, or None once every one is."""
        for point in self.points:
            if not point.captured:
                return point
        return None

    @property
    def captured_count(self) -> int:
        return sum(1 for p in self.points if p.captured)

    @property
    def complete(self) -> bool:
        return self.outstanding is None

    # -- capturing

    def store(self, index: int, capture: PointCapture) -> SessionPoint:
        """Attach one point's reads, whatever took them."""
        if not 0 <= index < len(self.points):
            raise SessionError(
                f"point {index} is outside this session's {len(self.points)} points"
            )
        point = self.points[index]
        point.capture = capture
        point.reads_per_station = {s.station: s.reads for s in capture.samples}
        # A new capture invalidates a solve taken over the old reads.
        self.stations = []
        self.saved_path = None
        self.saved_id = ""
        self.saved = None
        return point

    def store_reads(self, reads: list) -> SessionPoint | None:
        """Store a capture the robot took on its own as the outstanding point.

        This is the robot's button answering the prompt: whichever capture
        arrives while point k is outstanding is point k. Returns None when
        nothing is outstanding, so the caller can say so and drop it.
        """
        point = self.outstanding
        if point is None:
            return None
        return self.store(point.index, samples_from_reads(reads, point.index))

    def capture(self, stream, on_progress: Callable | None = None) -> SessionPoint:
        """Take the outstanding point's reads over `stream`, a `CaptureSession`."""
        point = self.outstanding
        if point is None:
            raise SessionError("every point of this session is already captured")
        point.reads_target = self.reads
        point.reads_per_station = {}

        def on_read(done: int, total: int, collected: list) -> None:
            counts: dict[int, int] = {}
            for read in collected:
                for record in read:
                    counts[record.lh_index] = counts.get(record.lh_index, 0) + 1
            point.reads_per_station = counts
            if on_progress is not None:
                on_progress(point)

        capture = stream.capture_point(
            point=point.index,
            reads=self.reads,
            timeout=self.timeout,
            retries=self.retries,
            on_read=on_read,
        )
        return self.store(point.index, capture)

    def redo(self) -> SessionPoint:
        """Discard the last captured point's reads and re-open it."""
        captured = [p for p in self.points if p.captured]
        if not captured:
            raise SessionError("nothing captured yet, so there is nothing to redo")
        point = captured[-1]
        point.capture = None
        point.reads_per_station = {}
        point.reads_target = 0
        self.stations = []
        self.saved_path = None
        self.saved_id = ""
        self.saved = None
        return point

    # -- solving and saving

    def placement(self) -> Placement:
        """The evidence, in the shape the solver and the writer read."""
        samples = []
        for point in self.points:
            if point.capture is not None:
                samples.extend(point.capture.samples)
        return Placement(
            index=0,
            at=self.at,
            points_mm=[p.mm for p in self.points],
            captured_at=datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            samples=samples,
        )

    def manager(self, placement: Placement | None = None) -> LighthouseManager:
        """The solver, over this session's placement and its site."""
        return LighthouseManager(
            placements=[placement or self.placement()],
            site=self.site,
            valid_mm=self.site.valid_mm or VALID_MM_DEFAULT,
            robot=self.robot,
        )

    def solve(self) -> list[StationSolution]:
        """Solve every station the captured points hold samples for."""
        if not self.complete:
            raise SessionError(
                f"{self.captured_count} of {len(self.points)} points captured; "
                "capture the rest before solving"
            )
        manager = self.manager()
        self.stations = manager.solve()
        self.unsolved = manager.unsolved_stations
        return self.stations

    def save(self, tag: str | None = None) -> Calibration:
        """Solve if needed, write the schema 2 file, and read back its id."""
        placement = self.placement()
        manager = self.manager(placement)
        self.stations = manager.solve()
        self.unsolved = manager.unsolved_stations
        path = manager.save_calibration(tag=tag or self.tag or None)
        calibration = read_calibration_file(path)
        self.saved_path = str(path)
        self.saved_id = calibration.id
        self.saved = calibration
        return calibration

    # -- the shape every client renders

    def as_dict(self) -> dict:
        """The whole session, as the REST routes and the WebSocket carry it."""
        return {
            "at": self.at,
            "site": self.site.name,
            "area": self.area,
            "device": self.device,
            "reads": self.reads,
            "status": self.status,
            "outstanding": None if self.complete else self.outstanding.index,
            "captured": self.captured_count,
            "total": len(self.points),
            "expected_error_mm": self.expected_error_mm,
            "points": [_point_dict(p) for p in self.points],
            "stations": [
                {
                    "index": s.index,
                    "points": s.points,
                    "residual_mm": s.residual_mm,
                    "solved_from": s.solved_from,
                }
                for s in self.stations
            ],
            "unsolved": [
                {"index": index, "points": seen} for index, seen in self.unsolved
            ],
            "saved_path": self.saved_path,
            "saved_id": self.saved_id,
            "error": self.error,
        }

    @property
    def status(self) -> str:
        """collecting while a point is outstanding, then solved, then saved."""
        if self.saved_id:
            return "saved"
        if self.stations:
            return "solved"
        return "collecting"

    def push_payload(self) -> bytes:
        """The saved calibration as the float32 calibration messages."""
        if self.saved is None:
            raise SessionError("nothing saved yet, so there is nothing to push")
        return calibration_payload(self.saved)


def placement_dict(index: int, placement: PointPlacement) -> dict:
    """One resolved point, with nothing captured at it yet."""
    x, y = placement.mm
    return {
        "index": index,
        "x": x,
        "y": y,
        "corner": placement.corner,
        "area": placement.area,
        "where": placement.where,
        "how": placement.how,
        "nose": placement.nose,
        "captured": False,
        "reads": [],
        "dropped": 0,
    }


def _point_dict(point: SessionPoint) -> dict:
    return {
        **placement_dict(point.index, point.placement),
        "captured": point.captured,
        "reads": [
            {
                "station": station,
                "reads": count,
                "target": point.reads_target or count,
            }
            for station, count in sorted(point.reads_per_station.items())
        ],
        "dropped": (point.capture.drop_count if point.capture else 0),
    }
