# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Filip Maksimovic <filip.maksimovic@inria.fr>
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""LH2 calibration: the site, the placements, the solve, and the file.

A calibration maps one basestation's camera points into a site's frame. It
is solved by least squares from the placements, each a set of points whose
frame coordinates are known and the raw counts every visible station read
there, and it is stored with that evidence plus a deterministic identity.
"""

# pylint: disable=invalid-name,unspecified-encoding,no-member

import dataclasses
import datetime
import hashlib
import math
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np

from dotbot.robots import ROBOT_DEFAULT
from dotbot.site import SITE_DEFAULT, Site

# cv2 is imported lazily inside `compute_homography_matrix` (the only
# function that uses it), so reading and writing calibration files works
# without opencv-python installed.

CALIBRATION_DIR = Path.home() / ".dotbot"
CALIBRATION_SUBDIR = "calibrations"
CALIBRATION_TOML_GLOB = "calibration-*.toml"
CALIBRATION_SCHEMA_VERSION = 2

# [x_min, y_min, x_max, y_max] in frame mm: outside it a reported position is
# implausible and the bot drops it. A site with a known extent supplies its
# own fence; this is what a site without one falls back to.
VALID_MM_DEFAULT = (0, 0, 4000, 4500)

LH2_BASESTATION_COUNT_MAX = 16

LH_PERIODS = [
    959000,  # mode 1
    957000,  # mode 2
    953000,  # mode 3
    949000,  # mode 4
    947000,  # mode 5
    943000,  # mode 6
    941000,  # mode 7
    939000,  # mode 8
    937000,  # mode 9
    929000,  # mode 10
    919000,  # mode 11
    911000,  # mode 12
    907000,  # mode 13
    901900,  # mode 14
    893000,  # mode 15
    887000,  # mode 16
]


@dataclass
class LH2Homography:
    """One basestation's homography, camera points to frame millimetres."""

    matrix: np.ndarray = dataclasses.field(
        default_factory=lambda: np.zeros((3, 3), dtype=np.float64)
    )


@dataclass
class LH2Counts:
    """One read of a station's two sweep counts."""

    lh_index: int
    count1: float
    count2: float

    def __repr__(self):
        return f"{dataclasses.asdict(self)}"


@dataclass
class LH2CalibrationSample:
    """One decoded capture record, as the transport delivers it."""

    lh_index: int
    count1: int
    count2: int
    ref_lh_index: Optional[int] = None
    ref_count1: Optional[int] = None
    ref_count2: Optional[int] = None

    def __post_init__(self):
        self.lh_index = int(self.lh_index)
        self.count1 = int(self.count1)
        self.count2 = int(self.count2)
        if self.ref_lh_index is not None:
            self.ref_lh_index = int(self.ref_lh_index)
        if self.ref_count1 is not None:
            self.ref_count1 = int(self.ref_count1)
        if self.ref_count2 is not None:
            self.ref_count2 = int(self.ref_count2)


@dataclass
class Sample:
    """The n reads one station took at one point of one placement."""

    station: int
    point: int
    count1: list[int] = field(default_factory=list)
    count2: list[int] = field(default_factory=list)

    @property
    def reads(self) -> int:
        return min(len(self.count1), len(self.count2))

    def mean_counts(self) -> LH2Counts:
        """The reads averaged, which is what reaches the solver."""
        if self.reads == 0:
            raise ValueError(
                f"station {self.station} point {self.point}: no reads to average"
            )
        return LH2Counts(
            lh_index=self.station,
            count1=float(np.mean(self.count1[: self.reads])),
            count2=float(np.mean(self.count2[: self.reads])),
        )

    def spread_mm(self) -> tuple[float, float]:
        """Per-count standard deviation of the reads, the stillness guard's input."""
        if self.reads < 2:
            return (0.0, 0.0)
        return (
            float(np.std(self.count1[: self.reads])),
            float(np.std(self.count2[: self.reads])),
        )


@dataclass
class Placement:
    """One capture at known points, plus what every visible station saw.

    `at` records what the operator typed and nothing reads it back;
    `points_mm` is resolved once, at capture, and is the only solver input.
    """

    index: int
    points_mm: list[tuple[float, float]]
    at: str = ""
    captured_at: str = ""
    samples: list[Sample] = field(default_factory=list)

    def stations(self) -> list[int]:
        return sorted({s.station for s in self.samples})

    def samples_for(self, station: int) -> list[Sample]:
        return sorted(
            (s for s in self.samples if s.station == station),
            key=lambda s: s.point,
        )


@dataclass
class StationSolution:
    """One station's solved homography and how well it fits its own evidence."""

    index: int
    homography: list[list[float]]
    points: int
    residual_mm: float
    solved_from: str = "direct"

    @property
    def matrix(self) -> np.ndarray:
        return np.array(self.homography, dtype=np.float64)


@dataclass
class Calibration:
    """A whole calibration file, in memory."""

    # The file records the site's name and anchor only, so a site read back
    # from one carries no extent and no areas.
    site: Site = field(default_factory=Site)
    valid_mm: tuple[int, int, int, int] = VALID_MM_DEFAULT
    placements: list[Placement] = field(default_factory=list)
    stations: list[StationSolution] = field(default_factory=list)
    created_at: str = ""
    tag: str = ""
    robot: str = ROBOT_DEFAULT
    path: Optional[Path] = None
    # The id the file on disk declares, when this came from one. A mismatch
    # with `id` means the file was hand-edited into a different calibration.
    stored_id: str = ""

    @property
    def id(self) -> str:
        return calibration_id(self)

    @property
    def id8(self) -> str:
        return self.id[:8]

    def station(self, index: int) -> Optional[StationSolution]:
        for station in self.stations:
            if station.index == index:
                return station
        return None


def calculate_camera_point(counts: LH2Counts) -> np.ndarray:
    """Turn one station's two sweep counts into a camera point."""
    period = LH_PERIODS[counts.lh_index]

    a1 = (counts.count1 * 8 / period) * 2 * math.pi
    a2 = (counts.count2 * 8 / period) * 2 * math.pi

    cam_x = -math.tan(0.5 * (a1 + a2))
    if counts.count1 < counts.count2:
        cam_y = -math.sin(a2 / 2 - a1 / 2 - 60 * math.pi / 180) / math.tan(math.pi / 6)
    else:
        cam_y = -math.sin(a1 / 2 - a2 / 2 - 60 * math.pi / 180) / math.tan(math.pi / 6)

    return np.asarray([cam_x, cam_y], dtype=np.float64)


def counts_for_camera_point(cam_x: float, cam_y: float, lh_index: int = 0) -> LH2Counts:
    """Inverse of `calculate_camera_point`: the counts that camera point gives.

    What a station would have reported for a point in its own view, which is
    how synthetic captures are built.
    """
    period = LH_PERIODS[lh_index]
    half_sum = math.atan(-cam_x)
    half_diff = math.pi / 3 + math.asin(-cam_y * math.tan(math.pi / 6))
    a1, a2 = half_sum - half_diff, half_sum + half_diff
    while a1 < 0:
        a1 += math.pi
        a2 += math.pi
    scale = period / 8 / (2 * math.pi)
    return LH2Counts(lh_index, a1 * scale, a2 * scale)


def camera_points_from_counts(counts: list[LH2Counts]) -> np.ndarray:
    """Convert counts to camera points."""
    camera_points = np.zeros((len(counts), 2), dtype=np.float64)
    for index, count in enumerate(counts):
        camera_points[index] = calculate_camera_point(count)
    return camera_points


def compute_homography_matrix(
    camera_points: np.ndarray,
    reference_points: np.ndarray,
) -> np.ndarray:
    """Least squares over every correspondence, camera points to frame mm.

    Four points fix the eight unknowns exactly; more over-determine them and
    give a residual.
    """
    import cv2  # lazy: opencv-python is only required for the solve

    if len(camera_points) < 4:
        raise ValueError(
            f"a homography needs at least 4 correspondences, got {len(camera_points)}"
        )

    M, _ = cv2.findHomography(camera_points, reference_points, method=0)

    if M is None:
        raise ValueError("Cannot find a valid homography matrix.")

    return M


def apply_homography(
    homography: np.ndarray, camera_view_points: np.ndarray
) -> np.ndarray:
    """Apply homography to camera points."""
    ground_plane_coordinates = np.zeros((0, 2), dtype=np.float64)
    for row in camera_view_points:
        projected = np.dot(homography, np.array([row[0], row[1], 1.0]))
        projected /= projected[2]
        ground_plane_coordinates = np.vstack((ground_plane_coordinates, projected[:2]))

    return ground_plane_coordinates


def reprojection_residual_mm(
    homography: np.ndarray,
    camera_points: np.ndarray,
    reference_points: np.ndarray,
) -> float:
    """RMS distance, in floor millimetres, between the solve and its evidence.

    Exactly zero with four points, where the fit is exact; the self-check
    with more.
    """
    projected = apply_homography(homography, camera_points)
    errors = np.linalg.norm(projected - np.asarray(reference_points), axis=1)
    return float(np.sqrt(np.mean(errors**2)))


def homography_as_bytes(matrix: np.ndarray) -> bytes:
    """THE SHIM: pack a homography as nine int32, the value times 1e3, truncated.

    The only place a homography is quantised, and it exists solely so a
    schema 2 calibration can reach firmware that still reads the int32 x 1e3
    encoding. It is deleted in the float32 firmware wave, along with its
    callers: the controller's push payload, the config-page writer and
    `calibration_payload_int32`, which the CLI push sends.
    """
    matrix_bytes = bytearray()
    try:
        for bytes_block in [
            int(n * 1e3).to_bytes(4, "little", signed=True) for n in matrix.ravel()
        ]:
            matrix_bytes += bytes_block
    except Exception:  # noqa: BLE001 - defensive fallback for overflow
        matrix_bytes = bytearray(36)
    return matrix_bytes


def calibration_payload_int32(stations) -> bytes:
    """The push payload for firmware that reads int32 x 1e3.

    A count byte, then `homography_as_bytes` per station in index order:
    the same layout as `wire.calibration_payload`, quantised through the
    shim. Deleted with it.
    """
    ordered = sorted(stations, key=lambda s: s.index)
    if not ordered:
        raise ValueError("calibration carries no solved station")
    payload = bytearray([len(ordered)])
    for station in ordered:
        payload += homography_as_bytes(station.matrix)
    return bytes(payload)


def _slug_tag(tag: str) -> str:
    """Filename-safe slug for a free-form calibration tag.

    Keeps ASCII letters, digits, dot, dash and underscore; collapses any
    other run of characters to a single dash and trims dashes and dots off
    the ends, so a tag like "../x" cannot smuggle in a leading "..". Returns
    "" when nothing usable remains.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "-", tag).strip("-.")


# --- Identity ---------------------------------------------------------------


def _num(value: float) -> str:
    """A float in the form that round-trips through the file byte for byte."""
    return repr(float(value))


def canonical_serialisation(calibration: Calibration) -> str:
    """The text the calibration id is the digest of.

    One `key=value` line per hashed field, sorted, newline-joined. The rule
    that decides membership: if changing a field cannot change any computed
    position, it is not here. So the site's `anchor`, `created_at`, `tag`,
    the robot model and a placement's `at` note are all outside it, and a
    typo fix in a sentence no code reads cannot make a fleet look stale.

    Zero is the site's anchor by definition, so there is no origin offset to
    hash: a reframe shifts the stored points and re-solves, which the
    `points_mm` and homography lines already cover.
    """
    lines = [
        f"schema_version={CALIBRATION_SCHEMA_VERSION}",
        f"site.name={calibration.site.name}",
        "validity.valid_mm=" + ",".join(_num(v) for v in calibration.valid_mm),
    ]
    for placement in calibration.placements:
        key = f"placement.{placement.index}"
        lines.append(
            f"{key}.points_mm="
            + ";".join(f"{_num(x)},{_num(y)}" for x, y in placement.points_mm)
        )
        for sample in sorted(placement.samples, key=lambda s: (s.station, s.point)):
            base = f"{key}.sample.{sample.station}.{sample.point}"
            lines.append(base + ".count1=" + ",".join(str(c) for c in sample.count1))
            lines.append(base + ".count2=" + ",".join(str(c) for c in sample.count2))
    for station in sorted(calibration.stations, key=lambda s: s.index):
        key = f"station.{station.index}"
        lines.append(f"{key}.solved_from={station.solved_from}")
        lines.append(f"{key}.points={station.points}")
        lines.append(f"{key}.residual_mm={_num(station.residual_mm)}")
        lines.append(
            f"{key}.homography="
            + ";".join(",".join(_num(v) for v in row) for row in station.homography)
        )
    return "\n".join(sorted(lines))


def calibration_id(calibration: Calibration) -> str:
    """Truncated SHA-256 over the canonical serialisation, 16 hex characters."""
    digest = hashlib.sha256(
        canonical_serialisation(calibration).encode("utf-8")
    ).hexdigest()
    return digest[:16]


# --- File -------------------------------------------------------------------


def calibration_root() -> Path:
    """Directory holding one subdirectory per site."""
    return CALIBRATION_DIR / CALIBRATION_SUBDIR


def site_dir(site_name: str) -> Path:
    """Where a site's calibration files live."""
    return calibration_root() / site_name


def _toml_int_list(values: Iterable[float]) -> str:
    return "[" + ", ".join(str(int(v)) for v in values) + "]"


def _toml_points(points: Sequence[Sequence[float]]) -> str:
    return "[" + ", ".join(f"[{_num(p[0])}, {_num(p[1])}]" for p in points) + "]"


def _toml_matrix(matrix: Sequence[Sequence[float]]) -> str:
    rows = ", ".join("[" + ", ".join(_num(v) for v in row) + "]" for row in matrix)
    return f"[{rows}]"


def _toml_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def render_calibration(calibration: Calibration) -> str:
    """The schema 2 file, as text."""
    site = calibration.site
    out = [
        f"schema_version = {CALIBRATION_SCHEMA_VERSION}",
        "",
        "[metadata]",
        f'created_at = "{calibration.created_at}"',
        f'id = "{calibration.id}"',
        f'robot = "{calibration.robot}"',
    ]
    if calibration.tag:
        out.append(f'tag = "{_toml_escape(calibration.tag)}"')
    out += [
        "",
        "[site]",
        f'name = "{site.name}"',
        f'anchor = "{_toml_escape(site.anchor)}"',
        "",
        "[validity]",
        f"valid_mm = {_toml_int_list(calibration.valid_mm)}",
    ]
    for placement in calibration.placements:
        out += [
            "",
            "[[placement]]",
            f"index = {placement.index}",
            f'at = "{_toml_escape(placement.at)}"',
            f"points_mm = {_toml_points(placement.points_mm)}",
            f'captured_at = "{placement.captured_at}"',
            "samples = [",
        ]
        for sample in sorted(placement.samples, key=lambda s: (s.station, s.point)):
            counts1 = ", ".join(str(c) for c in sample.count1)
            counts2 = ", ".join(str(c) for c in sample.count2)
            out.append(
                f"  {{ station = {sample.station}, point = {sample.point}, "
                f"count1 = [{counts1}], count2 = [{counts2}] }},"
            )
        out.append("]")
    for station in sorted(calibration.stations, key=lambda s: s.index):
        out += [
            "",
            "[[station]]",
            f"index = {station.index}",
            f'solved_from = "{station.solved_from}"',
            f"points = {station.points}",
            f"residual_mm = {_num(station.residual_mm)}",
            f"homography = {_toml_matrix(station.homography)}",
        ]
    return "\n".join(out) + "\n"


def read_calibration_file(path: Path) -> Calibration:
    """Parse a schema 2 calibration file.

    A file of any other schema version is rejected: there is no upgrade path,
    because a schema 1 file carries a packed payload and no site.
    """
    path = Path(path)
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    schema = data.get("schema_version", 0)
    if schema != CALIBRATION_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: unsupported calibration schema_version {schema} "
            f"(this build supports {CALIBRATION_SCHEMA_VERSION})"
        )
    if "frame" in data:
        raise ValueError(
            f"{path}: [frame] is not a table of this format. A calibration "
            "records the site it was captured in: [site] with name and "
            "anchor, zero being the anchor itself."
        )
    metadata = data.get("metadata", {})
    site_data = data.get("site", {})
    site = Site(
        name=site_data.get("name", SITE_DEFAULT),
        anchor=site_data.get("anchor", ""),
    )
    valid_mm = tuple(data.get("validity", {}).get("valid_mm", VALID_MM_DEFAULT))

    placements = []
    for raw in data.get("placement", []):
        samples = [
            Sample(
                station=int(s["station"]),
                point=int(s["point"]),
                count1=[int(c) for c in s["count1"]],
                count2=[int(c) for c in s["count2"]],
            )
            for s in raw.get("samples", [])
        ]
        placements.append(
            Placement(
                index=int(raw["index"]),
                points_mm=[(float(p[0]), float(p[1])) for p in raw["points_mm"]],
                at=raw.get("at", ""),
                captured_at=raw.get("captured_at", ""),
                samples=samples,
            )
        )

    stations = [
        StationSolution(
            index=int(raw["index"]),
            homography=[[float(v) for v in row] for row in raw["homography"]],
            points=int(raw.get("points", 0)),
            residual_mm=float(raw.get("residual_mm", 0.0)),
            solved_from=raw.get("solved_from", "direct"),
        )
        for raw in data.get("station", [])
    ]

    calibration = Calibration(
        site=site,
        valid_mm=valid_mm,
        placements=placements,
        stations=stations,
        created_at=metadata.get("created_at", ""),
        tag=metadata.get("tag", ""),
        robot=metadata.get("robot", ROBOT_DEFAULT),
        path=path,
    )
    calibration.stored_id = str(metadata.get("id", ""))
    return calibration


def resolve_calibration_path(
    spec: str,
    root: Optional[Path] = None,
    site: Optional[str] = None,
) -> Path:
    """The file `spec` names: a path, or an id prefix under a site directory.

    Never "the newest": a calibration in use is always the one named. An
    ambiguous id prefix is an error that lists the matches. `site` limits
    the search to that site's directory, so an id prefix cannot resolve to
    another site's calibration.
    """
    candidate = Path(spec).expanduser()
    if candidate.is_file():
        return candidate

    root = root or calibration_root()
    matches = sorted(
        path
        for path in root.glob(f"{site or '*'}/{CALIBRATION_TOML_GLOB}")
        if _file_id(path).startswith(spec.lower())
    )
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(
            f"no calibration matches {spec!r}: it is neither a readable file nor "
            f"the id prefix of a file under {root / (site or '*')}"
        )
    listed = "\n  ".join(str(m) for m in matches)
    raise ValueError(
        f"calibration id prefix {spec!r} matches several files:\n  {listed}"
    )


def _file_id(path: Path) -> str:
    """The id a file declares, read without solving anything."""
    try:
        with open(path, "rb") as handle:
            return str(tomllib.load(handle).get("metadata", {}).get("id", "")).lower()
    except (OSError, tomllib.TOMLDecodeError):
        return ""


def load_calibration(
    spec: str,
    root: Optional[Path] = None,
    site: Optional[str] = None,
) -> Calibration:
    """Read the calibration `spec` names."""
    return read_calibration_file(resolve_calibration_path(spec, root, site))


# --- Manager ----------------------------------------------------------------


class LighthouseManager:
    """Solve a calibration from its placements and write it out."""

    def __init__(
        self,
        placements: Optional[Sequence[Placement]] = None,
        site: Optional[Site] = None,
        valid_mm: Sequence[int] = VALID_MM_DEFAULT,
        robot: str = ROBOT_DEFAULT,
        extra_lh_num: int = 0,
    ):
        self.placements: list[Placement] = list(placements or [])
        self.site = site or Site()
        self.valid_mm = tuple(int(v) for v in valid_mm)
        self.robot = robot
        self.extra_lh_num = extra_lh_num
        self.stations: list[StationSolution] = []
        self.unsolved_stations: list[tuple[int, int]] = []
        self.homographies: list[LH2Homography] = [LH2Homography()] * (1 + extra_lh_num)
        self.last_saved_toml_path: Optional[Path] = None

    # -- solving

    def correspondences(self, station: int) -> tuple[np.ndarray, np.ndarray]:
        """Every (camera point, frame mm) pair this station contributes."""
        camera: list[LH2Counts] = []
        reference: list[tuple[float, float]] = []
        for placement in self.placements:
            for sample in placement.samples_for(station):
                if sample.point >= len(placement.points_mm):
                    raise ValueError(
                        f"placement {placement.index}: sample point {sample.point} "
                        f"has no declared coordinate"
                    )
                camera.append(sample.mean_counts())
                reference.append(placement.points_mm[sample.point])
        return (
            camera_points_from_counts(camera),
            np.array(reference, dtype=np.float64),
        )

    def solve_station(self, station: int) -> StationSolution:
        """One station's homography, by least squares over every point it saw."""
        camera_points, reference_points = self.correspondences(station)
        homography = compute_homography_matrix(camera_points, reference_points)
        residual = reprojection_residual_mm(homography, camera_points, reference_points)
        return StationSolution(
            index=station,
            homography=[[float(v) for v in row] for row in homography],
            points=len(camera_points),
            residual_mm=residual,
        )

    def solve(self) -> list[StationSolution]:
        """Solve every station the placements hold samples for."""
        stations = sorted({s.station for p in self.placements for s in p.samples})
        if not stations:
            raise ValueError("no samples to solve: every placement is empty")
        if len(stations) > LH2_BASESTATION_COUNT_MAX:
            raise ValueError(
                f"{len(stations)} stations exceeds the LH2 limit "
                f"({LH2_BASESTATION_COUNT_MAX})"
            )
        solved: list[StationSolution] = []
        unsolved: list[tuple[int, int]] = []
        for station in stations:
            camera_points, _ = self.correspondences(station)
            if len(camera_points) < 4:
                unsolved.append((station, len(camera_points)))
                continue
            solved.append(self.solve_station(station))
        if not solved:
            seen = ", ".join(f"station {i} at {n} point(s)" for i, n in unsolved)
            raise ValueError(f"no station has the 4 points a homography needs: {seen}")
        self.stations = solved
        self.unsolved_stations = unsolved
        self.homographies = [LH2Homography()] * (
            max((s.index for s in solved), default=-1) + 1
        )
        for station in solved:
            self.homographies[station.index] = LH2Homography(matrix=station.matrix)
        return solved

    def compute_calibration(
        self, calibration_samples: Optional[list[LH2CalibrationSample]] = None
    ) -> list[StationSolution]:
        """Solve from the placements, or from a flat list of single reads.

        The flat form is what the serial capture path holds: one read per
        point in the first placement's `points_mm` order, plus chained
        records for any extra station.
        """
        if calibration_samples is not None:
            self._adopt_flat_samples(calibration_samples)
        return self.solve()

    def _adopt_flat_samples(
        self, calibration_samples: list[LH2CalibrationSample]
    ) -> None:
        """Fold single-read records into the first placement's samples."""
        if not self.placements:
            raise ValueError("no placement to attach the samples to")
        placement = self.placements[0]
        placement.samples = []
        per_station: dict[int, int] = {}
        for record in calibration_samples:
            if record is None:
                continue
            point = per_station.get(record.lh_index, 0)
            per_station[record.lh_index] = point + 1
            placement.samples.append(
                Sample(
                    station=record.lh_index,
                    point=point,
                    count1=[record.count1],
                    count2=[record.count2],
                )
            )

    def has_calibration(self, lh_index) -> bool:
        """Whether a solved homography exists for a lighthouse index."""
        return len(self.homographies) > lh_index and not np.all(
            self.homographies[lh_index].matrix == 0
        )

    def ground_coordinate_from_counts(self, counts: LH2Counts) -> np.ndarray:
        """Convert counts to frame coordinates using the station's homography."""
        camera_points = np.zeros((1, 2), dtype=np.float64)
        camera_points[0] = calculate_camera_point(counts)
        return apply_homography(
            self.homographies[counts.lh_index].matrix, camera_points
        )[0]

    # -- persistence

    def calibration(self, tag: Optional[str] = None) -> Calibration:
        """The in-memory calibration this manager has solved."""
        now = datetime.datetime.now(datetime.timezone.utc)
        return Calibration(
            site=self.site,
            valid_mm=self.valid_mm,
            placements=self.placements,
            stations=self.stations or [],
            created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            tag=_slug_tag(tag) if tag else "",
            robot=self.robot,
        )

    def save_calibration(self, tag: Optional[str] = None) -> Path:
        """Write the calibration into its site's directory.

        The filename carries the capture stamp and the first eight characters
        of the id, so the name an operator reads back is the name the bot
        reports.
        """
        calibration = self.calibration(tag=tag)
        return write_calibration(calibration)


def write_calibration(calibration: Calibration) -> Path:
    """Write `calibration` to `calibrations/<site>/calibration-<stamp>-<id8>.toml`."""
    stamp = (calibration.created_at or "").replace(":", "-")
    directory = site_dir(calibration.site.name)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"calibration-{stamp}-{calibration.id8}.toml"
    # Explicit UTF-8: TOML is spec'd as UTF-8, and Path.write_text defaults to
    # the platform encoding, which mangles any non-ASCII byte.
    path.write_text(render_calibration(calibration), encoding="utf-8")
    calibration.path = path
    return path
