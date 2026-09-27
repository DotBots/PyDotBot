"""Tests for loading the vendored control core and calling across its ABI."""

import builtins
import hashlib
import json
import subprocess
import sys

import numpy as np
import pytest
from dotbot_utils.protocol import Packet

from dotbot.protocol import PayloadCommandMoveRaw, PayloadCommandWheelVelocity
from dotbot.sim import core as control


@pytest.fixture
def uncached():
    control._compiled.cache_clear()
    yield
    control._compiled.cache_clear()


def _packet(payload) -> bytes:
    return bytes(Packet.from_payload(payload).to_bytes())


def test_the_manifest_pins_the_vendored_file():
    manifest = json.loads(control.MANIFEST_PATH.read_text())
    digest = hashlib.sha256(control.WASM_PATH.read_bytes()).hexdigest()
    assert manifest["sha256"] == digest
    assert manifest["abi_version"] == control.ABI_VERSION
    assert len(manifest["commit"]) == 40


def test_the_core_loads_with_the_structs_it_declares():
    core = control.ControlCore(3)
    assert core.count == 3
    assert core.step(np.zeros(3, control.INPUT)).dtype == control.OUTPUT
    reports = core.reports()
    assert reports.dtype == control.REPORT
    assert (reports["direction"] == -1000).all()  # no heading from boot
    assert (reports["max_speed_10mm"] == 30).all()


def test_a_file_that_does_not_match_its_manifest_is_refused(
    tmp_path, monkeypatch, uncached
):
    manifest = json.loads(control.MANIFEST_PATH.read_text())
    manifest["sha256"] = "0" * 64
    path = tmp_path / "dotbot_control.json"
    path.write_text(json.dumps(manifest))
    monkeypatch.setattr(control, "MANIFEST_PATH", path)
    with pytest.raises(control.ControlCoreError, match="sha256"):
        control.ControlCore(1)


def test_an_abi_the_loader_does_not_speak_is_refused(monkeypatch, uncached):
    monkeypatch.setattr(control, "ABI_VERSION", control.ABI_VERSION + 1)
    with pytest.raises(control.ControlCoreError, match="ABI version"):
        control.ControlCore(1)


def test_without_wasmtime_the_core_says_what_to_install(monkeypatch, uncached):
    real_import = builtins.__import__

    def no_wasmtime(name, *args, **kwargs):
        if name == "wasmtime":
            raise ImportError("No module named 'wasmtime'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_wasmtime)
    with pytest.raises(control.ControlCoreError, match="pip install wasmtime"):
        control.ControlCore(1)


def test_the_rest_of_the_package_imports_without_wasmtime():
    code = (
        "import sys; sys.modules['wasmtime'] = None; "
        "import dotbot.adapter, dotbot.controller, dotbot.dotbot_simulator"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_a_command_reaches_only_the_robot_it_is_given_to():
    core = control.ControlCore(2)
    core.rx(
        0, _packet(PayloadCommandMoveRaw(left_x=0, left_y=80, right_x=0, right_y=80))
    )
    outputs = core.step(np.zeros(2, control.INPUT))
    # The app scales the joystick's +-127 to +-100 duty
    assert (outputs[0]["pwm_left"], outputs[0]["pwm_right"]) == (62, 62)
    assert (outputs[1]["pwm_left"], outputs[1]["pwm_right"]) == (0, 0)
    reports = core.reports()
    assert reports[0]["drive_mode"] == control.DriveMode.RAW
    assert reports[1]["drive_mode"] == control.DriveMode.IDLE


def test_an_oversized_command_is_dropped():
    core = control.ControlCore(1)
    packet = _packet(PayloadCommandWheelVelocity(left_mm_s=100, right_mm_s=100))
    core.rx(0, packet + bytes(core._rx_max))
    core.step(np.zeros(1, control.INPUT))
    assert core.reports()[0]["drive_mode"] == control.DriveMode.IDLE


def test_the_advertisement_starts_the_encoder_deltas_over():
    core = control.ControlCore(1)
    inputs = np.zeros(1, control.INPUT)
    inputs["counts_left"] = 7
    inputs["counts_right"] = -3
    core.step(inputs)
    first = core.advertisement(0, 2900)
    second = core.advertisement(0, 2900)
    assert len(first) == control.ADVERTISEMENT_BYTES
    # Type, calibration, direction, x, y, battery, duties, mode, then the deltas
    assert int.from_bytes(first[17:21], "little", signed=True) == 7
    assert int.from_bytes(first[21:25], "little", signed=True) == -3
    assert int.from_bytes(second[17:25], "little") == 0
    assert int.from_bytes(first[12:14], "little") == 2900


def test_a_seeded_robot_tracks_the_pose_it_is_given():
    core = control.ControlCore(3)
    core.seed(1, 1200.0, 800.0, -45.0)
    reports = core.reports()
    assert reports[1]["estimator_status"] == control.PoseStatus.TRACKING
    assert reports[1]["direction"] == -45
    assert (reports[1]["axle_x"], reports[1]["axle_y"]) == (1200, 800)
    assert reports[0]["direction"] == reports[2]["direction"] == -1000


def test_the_batched_advertisements_are_those_the_step_asked_for():
    core = control.ControlCore(4)
    inputs = np.zeros(4, control.INPUT)
    # Robots 1 and 3 reach their first advertisement, 500 ms, on this step
    inputs["elapsed_ticks"] = [1, 50, 1, 50]
    inputs["counts_left"] = [0, 11, 0, 13]
    outputs = core.step(inputs)
    assert outputs["advertise"].tolist() == [0, 1, 0, 1]
    indices, packets = core.advertisements(np.array([3000, 3001, 3002, 3003]))
    assert indices.tolist() == [1, 3]
    assert packets.shape == (2, control.ADVERTISEMENT_BYTES)
    assert [int.from_bytes(p[12:14], "little") for p in packets] == [3001, 3003]
    assert [int.from_bytes(p[17:21], "little") for p in packets] == [11, 13]
    empty_indices, empty_packets = core.advertisements(np.zeros(4))
    assert empty_indices.size == 0 and empty_packets.shape == (0, 42)
