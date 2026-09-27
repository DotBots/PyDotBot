# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The DotBot app's control core, run for a whole fleet in WebAssembly.

`dotbot_control.wasm` is DotBot-libs `drv/dotbot_control` built with
`make wasm`: the wheel loop, the pose estimator, the waypoint steering, the
command handling and the advertisement encoder the robot runs. Its source
commit, ABI version and sha256 are in `dotbot_control.json`, and all three
are checked when it loads. The structs below mirror `drv/dotbot_control.h`.
"""

import atexit
import functools
import hashlib
import json
from enum import IntEnum
from pathlib import Path

import numpy as np

ABI_VERSION = 2
WASM_PATH = Path(__file__).with_name("dotbot_control.wasm")
MANIFEST_PATH = Path(__file__).with_name("dotbot_control.json")

# db_control_input_t
INPUT = np.dtype(
    [
        ("counts_left", "<i4"),
        ("counts_right", "<i4"),
        ("fix_sequence", "<u4"),
        ("fix_x", "<u4"),
        ("fix_y", "<u4"),
        ("elapsed_ticks", "<u4"),
    ]
)
# db_control_output_t
OUTPUT = np.dtype(
    [
        ("pwm_left", "i1"),
        ("pwm_right", "i1"),
        ("brake_left", "u1"),
        ("brake_right", "u1"),
        ("write", "u1"),
        ("advertise", "u1"),
        ("reserved", "u1", 2),
    ]
)
# db_control_report_t
REPORT = np.dtype(
    [
        ("axle_x_mm", "<f4"),
        ("axle_y_mm", "<f4"),
        ("heading_deg", "<f4"),
        ("max_speed_mm_s", "<f4"),
        ("sensor_x", "<u4"),
        ("sensor_y", "<u4"),
        ("waypoint_x", "<u4"),
        ("waypoint_y", "<u4"),
        ("encoder_left", "<u4"),
        ("encoder_right", "<u4"),
        ("fix_sequence", "<u4"),
        ("direction", "<i2"),
        ("axle_x", "<u2"),
        ("axle_y", "<u2"),
        ("pwm_left", "i1"),
        ("pwm_right", "i1"),
        ("brake_left", "u1"),
        ("brake_right", "u1"),
        ("control_mode", "u1"),
        ("drive_mode", "u1"),
        ("steering_state", "u1"),
        ("estimator_status", "u1"),
        ("waypoint_index", "u1"),
        ("waypoint_count", "u1"),
        ("batch_id", "u1"),
        ("status", "u1"),
        ("reason", "u1"),
        ("max_speed_10mm", "u1"),
    ]
)
ADVERTISEMENT_BYTES = 42
# fleet_geometry_t: drv/geometry.h as the core was built, mm and degrees
GEOMETRY = np.dtype(
    [
        (name, "<f4")
        for name in (
            "wheel_diameter_mm",
            "track_mm",
            "encoder_cpr",
            "gear_ratio",
            "mm_per_count",
            "lever_arm_mm",
            "lever_angle_deg",
            "lever_arm_effective_mm",
            "track_effective_mm",
            "track_effective_arc_mm",
            "track_effective_arc_ratio",
        )
    ]
)


class DriveMode(IntEnum):
    """db_control_drive_mode_t: who writes the motors."""

    IDLE = 0
    RAW = 1
    VELOCITY = 2
    WAYPOINT = 3


class SteeringState(IntEnum):
    """db_steering_state_t"""

    IDLE = 0
    NO_HEADING = 1
    ALIGN = 2
    DRIVE = 3
    FINAL_TURN = 4
    ARRIVED = 5
    HOLD = 6
    FAILED = 7
    RECOVER = 8
    SETTLE = 9
    NUDGE = 10


class PoseStatus(IntEnum):
    """db_pose_estimator_status_t"""

    SEEDING = 0
    TRACKING = 1
    LOST = 2


class ControlCoreError(RuntimeError):
    """The control core cannot be loaded."""


def _wasmtime():
    try:
        import wasmtime
    except ImportError as exc:
        raise ControlCoreError(
            "The DotBot simulator runs the robots' control firmware in "
            "WebAssembly and needs the wasmtime package, which is not "
            "installed. Install it with `pip install wasmtime`; it has no "
            "build for 32-bit ARM, where the simulator is unavailable."
        ) from exc
    return wasmtime


@functools.lru_cache(maxsize=None)
def _compiled():
    """The engine, the compiled module and the manifest, once per process."""
    manifest = json.loads(MANIFEST_PATH.read_text())
    data = WASM_PATH.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != manifest["sha256"]:
        raise ControlCoreError(
            f"{WASM_PATH.name} has sha256 {digest}, but {MANIFEST_PATH.name} "
            f"pins {manifest['sha256']}"
        )
    if manifest["abi_version"] != ABI_VERSION:
        raise ControlCoreError(
            f"{MANIFEST_PATH.name} declares ABI version "
            f"{manifest['abi_version']}, this loader speaks {ABI_VERSION}"
        )
    wasmtime = _wasmtime()
    engine = wasmtime.Engine()
    return engine, wasmtime.Module(engine, data), manifest


# Freed before interpreter shutdown, which would otherwise tear down the
# wasmtime bindings first
atexit.register(_compiled.cache_clear)


class ControlCore:
    """`count` robots' control state, stepped together.

    Not thread-safe: every call must come from the thread that steps it.
    """

    def __init__(self, count: int):
        engine, module, self.manifest = _compiled()
        wasmtime = _wasmtime()
        self._store = wasmtime.Store(engine)
        exports = wasmtime.Instance(self._store, module, []).exports(self._store)
        self._memory = exports["memory"]
        self._fn = {
            export.name: exports[export.name]
            for export in module.exports
            if isinstance(exports[export.name], wasmtime.Func)
        }
        self._call("_initialize")
        self._check_abi()
        if self._call("fleet_init", count) != 0:
            raise MemoryError(f"the control core cannot hold {count} robots")
        self.count = count
        self._inputs = self._call("fleet_inputs")
        self._outputs = self._call("fleet_outputs")
        self._reports = self._call("fleet_report_buffer")
        self._rx_buffer = self._call("fleet_rx_buffer")
        self._advertisement = self._call("fleet_advertisement_buffer")
        self._battery = self._call("fleet_battery_buffer")
        self._advertisements = self._call("fleet_advertisements_buffer")
        self._rx_max = self._call("rx_max_bytes")

    def _call(self, name: str, *args):
        return self._fn[name](self._store, *args)

    def _check_abi(self):
        expected = {
            "abi_version": ABI_VERSION,
            "sizeof_input": INPUT.itemsize,
            "sizeof_output": OUTPUT.itemsize,
            "sizeof_report": REPORT.itemsize,
            "advertisement_bytes": ADVERTISEMENT_BYTES,
            "sizeof_geometry": GEOMETRY.itemsize,
        }
        for name, value in expected.items():
            actual = self._call(name)
            if actual != value:
                raise ControlCoreError(
                    f"{WASM_PATH.name}: {name}() is {actual}, expected {value}"
                )

    def geometry(self) -> np.void:
        """The GEOMETRY record the core was built with."""
        address = self._call("geometry")
        data = self._memory.read(self._store, address, address + GEOMETRY.itemsize)
        return np.frombuffer(data, GEOMETRY)[0]

    def seed(self, index: int, x_mm: float, y_mm: float, heading_deg: float):
        """Set robot `index`'s axle midpoint and heading outright, its
        estimator tracking them, as though it had acquired them."""
        self._call("fleet_seed", index, x_mm, y_mm, heading_deg)

    def rx(self, index: int, packet: bytes):
        """Hand robot `index` one command: the type byte, then the payload.
        A packet longer than the core accepts is dropped, as the robot does."""
        if not packet or len(packet) > self._rx_max:
            return
        self._memory.write(self._store, packet, self._rx_buffer)
        self._call("fleet_rx", index, self._rx_buffer, len(packet))

    def step(self, inputs: np.ndarray) -> np.ndarray:
        """One tick of every robot; `inputs` holds one INPUT per robot."""
        self._memory.write(self._store, inputs.tobytes(), self._inputs)
        self._call("fleet_step", self._inputs, self._outputs)
        data = self._memory.read(
            self._store, self._outputs, self._outputs + OUTPUT.itemsize * self.count
        )
        return np.frombuffer(data, OUTPUT)

    def reports(self) -> np.ndarray:
        """One REPORT per robot."""
        self._call("fleet_reports", self._reports)
        data = self._memory.read(
            self._store, self._reports, self._reports + REPORT.itemsize * self.count
        )
        return np.frombuffer(data, REPORT)

    def advertisement(self, index: int, battery: int) -> bytearray:
        """Robot `index`'s advertisement packet, type byte first. Starts the
        encoder deltas the next one carries."""
        length = self._call(
            "fleet_advertisement", index, battery & 0xFFFF, self._advertisement
        )
        return self._memory.read(
            self._store, self._advertisement, self._advertisement + length
        )

    def advertisements(self, battery: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The advertisement of every robot the last step asked one of, as
        (indices, packets): one row of ADVERTISEMENT_BYTES per index, type
        byte first. `battery` holds one level per robot. Starts those robots'
        encoder deltas over."""
        self._memory.write(
            self._store, battery.astype("<u2").tobytes(), self._battery
        )
        n = self._call("fleet_advertisements", self._battery, self._advertisements)
        if n == 0:
            return np.zeros(0, np.uint32), np.zeros((0, ADVERTISEMENT_BYTES), np.uint8)
        data = self._memory.read(
            self._store,
            self._advertisements,
            self._advertisements + n * (4 + ADVERTISEMENT_BYTES),
        )
        indices = np.frombuffer(data, "<u4", count=n)
        packets = np.frombuffer(data, np.uint8, offset=4 * n).reshape(
            n, ADVERTISEMENT_BYTES
        )
        return indices, packets
