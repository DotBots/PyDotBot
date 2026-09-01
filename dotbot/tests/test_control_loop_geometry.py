"""Guards the robot dimensions the simulator duplicates from the C control loop.

The compiled loop is the source: it is what runs on a robot. `dotbot_simulator`
keeps a copy so it can generate encoder counts that loop will read back
correctly, and nothing enforces the copy at build time.

Skips unless the library is built. Point `DOTBOT_CONTROL_LOOP_LIBRARY` at it, or
build it into `build/` per `utils/control_loop/README.md`.
"""

import ctypes
import os
from pathlib import Path

import pytest

from dotbot.dotbot_simulator import ENCODER_CPR, MM_PER_COUNT, D, L, R

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


@pytest.fixture(name="geometry")
def geometry_fixture() -> ControlLoopGeometry:
    path = _library_path()
    if path is None or not path.exists():
        pytest.skip(f"control loop library not built; set {LIBRARY_ENV}")
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


def test_lever_arm_is_exported(geometry):
    """Phase-5 estimator input: it is not in the Python copy yet, so only the
    export is checked."""
    assert geometry.lh2_lever_arm_mm > 0.0
