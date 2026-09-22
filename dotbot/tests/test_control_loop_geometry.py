"""Pins the Python geometry record to the C one in DotBot-libs `drv/geometry.h`.

The two cannot share a file at build time, so the record for the board the
library was built for is checked against the compiled
`control_loop_get_geometry()`, and so is the simulator that reads the record.

Skips unless the library is built. Point `DOTBOT_CONTROL_LOOP_LIBRARY` at it, or
build it into `build/` per `utils/control_loop/README.md`.
"""

import ctypes
import os
from pathlib import Path

import pytest

from dotbot.dotbot_simulator import ENCODER_CPR, MM_PER_COUNT, D, L, R
from dotbot.robots import ROBOTS

LIBRARY_ENV = "DOTBOT_CONTROL_LOOP_LIBRARY"
DEFAULT_BUILD_DIR = Path(__file__).resolve().parents[2] / "build"


class ControlLoopGeometry(ctypes.Structure):
    """Mirrors control_loop_geometry_t from control_loop.h."""

    _fields_ = [
        ("wheel_diameter_mm", ctypes.c_float),
        ("track_mm", ctypes.c_float),
        ("encoder_cpr", ctypes.c_float),
        ("gear_ratio", ctypes.c_float),
        ("mm_per_count", ctypes.c_float),
        ("lh2_lever_arm_mm", ctypes.c_float),
        ("lh2_lever_angle_deg", ctypes.c_float),
    ]


def _library_path() -> Path | None:
    configured = os.environ.get(LIBRARY_ENV)
    if configured:
        return Path(configured)
    for suffix in ("so", "dylib", "dll"):
        found = sorted(DEFAULT_BUILD_DIR.glob(f"*dotbot_control_loop*.{suffix}"))
        if found:
            return found[0]
    return None


def _built_model(path: Path) -> str:
    """The robot model the library was built for, from its CMake cache.

    Falls back to the CMake default, version 3, when there is no cache beside
    the library.
    """
    version = "3"
    cache = path.parent / "CMakeCache.txt"
    if cache.exists():
        for line in cache.read_text().splitlines():
            if line.startswith("DOTBOT_VERSION:"):
                version = line.partition("=")[2].strip()
    return f"dotbot-v{version}"


@pytest.fixture(name="library_path")
def library_path_fixture() -> Path:
    path = _library_path()
    if path is None or not path.exists():
        pytest.skip(f"control loop library not built; set {LIBRARY_ENV}")
    return path


@pytest.fixture(name="geometry")
def geometry_fixture(library_path) -> ControlLoopGeometry:
    path = library_path
    library = ctypes.CDLL(str(path))
    if not hasattr(library, "control_loop_get_geometry"):
        pytest.skip("library predates control_loop_get_geometry")
    geometry = ControlLoopGeometry()
    library.control_loop_get_geometry(ctypes.byref(geometry))
    return geometry


@pytest.mark.parametrize(
    "field,python_value",
    [
        ("wheel_diameter_mm", D),
        ("track_mm", L),
        ("encoder_cpr", ENCODER_CPR),
        ("gear_ratio", R),
        ("mm_per_count", MM_PER_COUNT),
    ],
)
def test_simulator_matches_compiled_geometry(geometry, field, python_value):
    assert getattr(geometry, field) == pytest.approx(python_value, rel=1e-6)


@pytest.fixture(name="record")
def record_fixture(library_path):
    model = _built_model(library_path)
    if model not in ROBOTS:
        pytest.skip(f"no geometry record for {model}")
    return ROBOTS[model]


@pytest.mark.parametrize(
    "field,record_field",
    [
        ("lh2_lever_arm_mm", "lever_arm_mm"),
        ("lh2_lever_angle_deg", "lever_angle_deg"),
        ("track_mm", "track_mm"),
        ("wheel_diameter_mm", "wheel_diameter_mm"),
        ("encoder_cpr", "encoder_cpr"),
        ("gear_ratio", "gear_ratio"),
        ("mm_per_count", "mm_per_count"),
    ],
)
def test_record_matches_compiled_geometry(geometry, record, field, record_field):
    assert getattr(geometry, field) == pytest.approx(
        getattr(record, record_field), rel=1e-6
    )
