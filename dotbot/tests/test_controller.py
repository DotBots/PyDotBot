"""Test module for controller base class."""

import asyncio
import pathlib
import time
from unittest.mock import MagicMock

import pytest
from dotbot_utils.hdlc import hdlc_encode
from dotbot_utils.protocol import Frame, Header, Packet
from dotbot_utils.serial_interface import SerialInterface

from dotbot import addr_to_hex
from dotbot.adapter import SerialAdapter
from dotbot.area import Area
from dotbot.controller import Controller, ControllerSettings, gps_distance, lh2_distance
from dotbot.models import (
    DotBotGPSPosition,
    DotBotLH2Position,
    DotBotModel,
    DotBotQueryModel,
    DotBotStatus,
)
from dotbot.protocol import ApplicationType, ControlModeType, PayloadControlMode
from dotbot.site import Site

# A measured site, which the package never ships.
C405 = Site(
    name="c405-arena",
    anchor="the arena's top-left corner, against the door wall of C405",
    extent_mm=(2000, 4000),
    areas={
        "annex": Area(0, 2000, 2000, 2000, "annex"),
        "wing": Area(2000, 2610, 1330, 1390, "wing"),
    },
)

# The 1 x 1 m patch a camera is registered over, in C405's frame.
DEV_CORNER = Area(1000, 0, 1000, 1000, "dev-corner")


@pytest.fixture
def serial_mock(monkeypatch):
    """Stub the serial port so a Controller can be built without hardware."""
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.write", MagicMock()
    )
    monkeypatch.setattr("dotbot_utils.serial_interface.serial.Serial.open", MagicMock())
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.flush", MagicMock()
    )


@pytest.fixture
def controller(monkeypatch):
    """Create a controller instance with mocked serial interface."""
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.write", MagicMock()
    )
    monkeypatch.setattr("dotbot_utils.serial_interface.serial.Serial.open", MagicMock())
    monkeypatch.setattr(
        "dotbot_utils.serial_interface.serial.Serial.flush", MagicMock()
    )
    settings = ControllerSettings(
        port="/dev/null",
        baudrate=115200,
        network_id="0",
        gw_address="78",
    )
    _controller = Controller(settings)
    _controller.dotbots.update(
        {
            "0000000000000000": DotBotModel(
                address="0000000000000000",
                last_seen=time.time(),
                application=ApplicationType.DotBot,
                status=DotBotStatus.ACTIVE,
                battery=2.0,
                lh2_position=DotBotLH2Position(x=1000, y=1000),
                position_history=[
                    DotBotLH2Position(x=900, y=900),
                    DotBotLH2Position(x=800, y=800),
                ],
            ),
            "0000000000000001": DotBotModel(
                address="0000000000000001",
                last_seen=time.time(),
                application=ApplicationType.SailBot,
                status=DotBotStatus.ACTIVE,
                battery=3.0,
            ),
            "0000000000000002": DotBotModel(
                address="0000000000000002",
                last_seen=time.time(),
                application=ApplicationType.DotBot,
                status=DotBotStatus.INACTIVE,
                battery=1.0,
                lh2_position=DotBotLH2Position(x=500, y=500),
                position_history=[
                    DotBotLH2Position(x=400, y=400),
                    DotBotLH2Position(x=300, y=300),
                ],
            ),
            "0000000000000003": DotBotModel(
                address="0000000000000003",
                last_seen=time.time(),
                application=ApplicationType.DotBot,
                status=DotBotStatus.LOST,
                battery=1.0,
                lh2_position=DotBotLH2Position(x=1000, y=1500),
                position_history=[],
            ),
        }
    )
    _controller.adapter = SerialAdapter(settings.port, settings.baudrate)
    _controller.adapter.serial = SerialInterface(
        settings.port, settings.baudrate, lambda: None
    )

    yield _controller


@pytest.mark.asyncio
async def test_controller(controller):
    """Check controller subclass instanciation and write to serial."""
    frame = Frame(
        header=Header(
            destination=0,
            source=0,
        ),
        packet=Packet().from_payload(PayloadControlMode(mode=ControlModeType.AUTO)),
    )
    controller.send_payload(0, PayloadControlMode(mode=ControlModeType.AUTO))

    serial_write_mock = controller.adapter.serial.serial.write
    assert serial_write_mock.call_count == 1
    payload_expected = hdlc_encode(frame.to_bytes())
    assert serial_write_mock.call_args_list[0].args[0] == payload_expected


@pytest.mark.asyncio
async def test_controller_dont_send(controller):
    """Check controller subclass instanciation and write to serial."""
    serial_write_mock = controller.adapter.serial.serial.write
    # DotBot is not in the controller known dotbot, so the payload won't be sent
    controller.send_payload(42, PayloadControlMode(mode=ControlModeType.AUTO))
    assert serial_write_mock.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,length",
    [
        pytest.param(
            DotBotQueryModel(address="0000000000000001"),
            1,
            id="by address",
        ),
        pytest.param(
            DotBotQueryModel(application=ApplicationType.SailBot),
            1,
            id="by application",
        ),
        pytest.param(
            DotBotQueryModel(status=DotBotStatus.ACTIVE),
            2,
            id="by status active",
        ),
        pytest.param(
            DotBotQueryModel(status=DotBotStatus.INACTIVE),
            1,
            id="by status inactive",
        ),
        pytest.param(
            DotBotQueryModel(status=DotBotStatus.LOST),
            1,
            id="by status lost",
        ),
        pytest.param(
            DotBotQueryModel(min_battery=2.5),
            1,
            id="by min battery",
        ),
        pytest.param(
            DotBotQueryModel(max_battery=1.5),
            2,
            id="by max battery",
        ),
        pytest.param(
            DotBotQueryModel(max_position_x=600),
            1,
            id="by max position x",
        ),
        pytest.param(
            DotBotQueryModel(min_position_x=800),
            2,
            id="by min position x",
        ),
        pytest.param(
            DotBotQueryModel(max_position_y=600),
            1,
            id="by max position y",
        ),
        pytest.param(
            DotBotQueryModel(min_position_y=1000),
            2,
            id="by min position y",
        ),
        pytest.param(
            DotBotQueryModel(max_positions=1),
            3,
            id="by max positions",
        ),
        pytest.param(
            DotBotQueryModel(limit=2),
            2,
            id="by limit",
        ),
    ],
)
async def test_controller_get_dotbots_query(query, length, controller):
    """Check controller get_dotbots query."""
    dotbots = controller.get_dotbots(query=query)
    assert len(dotbots) == length


def test_controller_sailbot_simulator():
    """Check controller called for sailbot simulator."""

    async def start_simulator():
        settings = ControllerSettings(
            adapter="sailbot-simulator",
            network_id="0",
            gw_address="78",
            controller_http_port=8002,
            headless=True,
        )
        controller = Controller(settings)
        try:
            await asyncio.wait_for(controller.run(), timeout=0.5)
        except asyncio.TimeoutError:
            pass

    asyncio.run(start_simulator())


def test_controller_dotbot_simulator():
    """Check controller called for dotbot simulator."""

    async def start_simulator():
        settings = ControllerSettings(
            adapter="dotbot-simulator",
            network_id="0",
            gw_address="78",
            controller_http_port=8001,
            headless=True,
        )
        controller = Controller(settings)
        try:
            await asyncio.wait_for(controller.run(), timeout=0.5)
        except asyncio.TimeoutError:
            pass

    asyncio.run(start_simulator())


@pytest.mark.parametrize(
    "last,new,result",
    [
        (DotBotLH2Position(x=0, y=0, z=0), DotBotLH2Position(x=0, y=0, z=0), 0.0),
        (DotBotLH2Position(x=1, y=0, z=0), DotBotLH2Position(x=0, y=0, z=0), 1.0),
        (DotBotLH2Position(x=0, y=1, z=0), DotBotLH2Position(x=0, y=0, z=0), 1.0),
    ],
)
def test_lh2_distance(last, new, result):
    assert lh2_distance(last, new) == result


@pytest.mark.parametrize(
    "last,new,result",
    [
        (
            DotBotGPSPosition(latitude=45.7597, longitude=4.8422),  # Lyon
            DotBotGPSPosition(latitude=48.8567, longitude=2.3508),  # Paris
            392216.71780,
        ),
        (
            DotBotGPSPosition(latitude=51.509865, longitude=-0.118092),  # London
            DotBotGPSPosition(latitude=48.8567, longitude=2.3508),  # Paris
            343374.07842,
        ),
    ],
)
def test_gps_distance(last, new, result):
    assert gps_distance(last, new) == pytest.approx(result)


@pytest.mark.parametrize(
    "addr,expected",
    [
        (0x217B829760EBA3E0, "217B829760EBA3E0"),
        (0x0, "0000000000000000"),
        (0xFFFFFFFFFFFFFFFF, "FFFFFFFFFFFFFFFF"),
        (0xABCDEF, "0000000000ABCDEF"),
    ],
)
def test_addr_to_hex_is_uppercase_and_padded(addr, expected):
    """Addresses render uppercase: swarmit joins the two planes on this string.

    `binascii.hexlify` returns lowercase, so a plain hexlify here silently
    produces a key that never matches the swarm side (nor
    DOTBOT_ADDRESS_DEFAULT / GATEWAY_ADDRESS_DEFAULT, both written uppercase).
    """
    assert addr_to_hex(addr) == expected
    assert addr_to_hex(addr) == addr_to_hex(addr).upper()


def _write_calibration(tmp_path, monkeypatch, site="site-a"):
    """Save a solved calibration under tmp_path and return its id."""
    import sys

    from dotbot.calibration import lighthouse2

    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import test_calibration_lighthouse2 as helpers

    monkeypatch.setattr(lighthouse2, "CALIBRATION_DIR", tmp_path)
    corners = [(-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)]
    manager = lighthouse2.LighthouseManager(
        placements=[helpers._consistent_placement(corners, reads=3)],
        site=Site(name=site),
    )
    manager.solve()
    path = manager.save_calibration()
    return lighthouse2.read_calibration_file(path)


def test_controller_loads_the_calibration_named_by_id(
    tmp_path, monkeypatch, serial_mock
):
    """An id prefix resolves under calibrations/<site>/, never the newest file."""
    import numpy as np

    from dotbot.controller import load_calibration

    written = _write_calibration(tmp_path, monkeypatch)
    settings = ControllerSettings(
        port="/dev/null",
        baudrate=115200,
        network_id="0",
        gw_address="78",
        site=Site(name="site-a"),
        lh2_calibration=written.id8,
    )
    controller = Controller(settings)

    assert controller.lh2_calibration
    assert controller.calibration.site.name == "site-a"
    assert (
        load_calibration(written.id8, site="site-a").path
        == tmp_path / "calibrations" / "site-a" / written.path.name
    )
    # The site scopes the lookup: the same id is not found under another.
    with pytest.raises(ValueError, match="no calibration matches"):
        load_calibration(written.id8, site="site-b")

    from dotbot.calibration.lighthouse2 import homography_as_float32
    from dotbot.protocol import PayloadLh2CalibrationHomography

    station = controller.lh2_calibration[0]
    payload = PayloadLh2CalibrationHomography(
        index=station.index,
        homography_matrix=homography_as_float32(station.homography),
    )
    # float32 on the bare-metal wire: no thousandth truncation.
    assert np.allclose(payload.matrix, written.stations[0].homography, rtol=1e-7)


def test_controller_with_no_calibration_loads_nothing(serial_mock):
    """No --lh2-calibration and no config key: nothing is loaded, and it is said."""
    settings = ControllerSettings(
        port="/dev/null", baudrate=115200, network_id="0", gw_address="78"
    )
    controller = Controller(settings)
    assert controller.lh2_calibration == []
    assert controller.calibration is None


def test_a_controller_keeps_the_site_it_was_given(serial_mock):
    settings = ControllerSettings(
        port="/dev/null",
        baudrate=115200,
        network_id="0",
        gw_address="78",
        site=C405,
    )
    controller = Controller(settings)
    assert controller.site.name == "c405-arena"
    assert sorted(controller.site.areas) == ["annex", "wing"]


def test_a_controller_with_no_site_keeps_the_neutral_one(serial_mock):
    settings = ControllerSettings(
        port="/dev/null",
        baudrate=115200,
        network_id="0",
        gw_address="78",
    )
    controller = Controller(settings)
    assert controller.site.name == "default"
    assert controller.site.areas == {}


def _write_camera_calibration(tmp_path, monkeypatch, source, area="dev-corner"):
    """A camera registration under tmp_path, over `source`, and its id."""
    from dotbot.camera import registration
    from dotbot.camera.sheets import marker_layout, span_mm

    monkeypatch.setattr(registration, "site_dir", lambda name: tmp_path / name)
    monkeypatch.setattr(registration, "calibration_root", lambda: tmp_path)
    calibration = registration.CameraCalibration(
        site=Site(name=C405.name, anchor=C405.anchor),
        area=area,
        source=str(source),
        width=64,
        height=48,
        fps=0.0,
        reads=1,
        markers=[
            registration.MarkerObservation(
                id=marker.id,
                centre_mm=marker.centre_mm,
                corners_mm=marker.corners_mm,
                corners_px=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            )
            for marker in marker_layout(DEV_CORNER)
        ],
        matrix=[[1.0, 0.0, 1000.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        residual_mm=0.4,
        span_mm=span_mm(marker_layout(DEV_CORNER)),
        created="2026-09-15T13:42:00Z",
    )
    registration.write_camera_calibration(calibration)
    return calibration


def _camera_site():
    """C405 with the area the camera covers, which C405 itself omits."""
    areas = dict(C405.areas)
    areas["dev-corner"] = DEV_CORNER
    return Site(
        name=C405.name, anchor=C405.anchor, extent_mm=C405.extent_mm, areas=areas
    )


def test_controller_serves_the_camera_layer_named_by_id(
    tmp_path, monkeypatch, serial_mock
):
    """An id prefix resolves under calibrations/<site>/, as --lh2-calibration does."""
    import cv2
    import numpy as np

    source = tmp_path / "frame.png"
    cv2.imwrite(str(source), np.full((48, 64), 180, np.uint8))
    written = _write_camera_calibration(tmp_path, monkeypatch, source)

    controller = Controller(
        ControllerSettings(
            port="/dev/null",
            baudrate=115200,
            network_id="0",
            gw_address="78",
            site=_camera_site(),
            camera_calibration=written.id8,
        )
    )
    try:
        assert len(controller.cameras) == 1
        served = controller.cameras[0]
        assert served.live
        assert served.area == DEV_CORNER
        assert served.calibration.id == written.id
        assert served.raster == (500, 500)
    finally:
        for camera_service in controller.cameras:
            camera_service.stop()


def test_controller_with_no_camera_calibration_serves_no_layer(serial_mock):
    settings = ControllerSettings(
        port="/dev/null", baudrate=115200, network_id="0", gw_address="78"
    )
    assert Controller(settings).cameras == []


def test_a_camera_calibration_for_an_area_this_site_lacks_serves_no_layer(
    tmp_path, monkeypatch, serial_mock
):
    """The file names an area; the running site is what has to define it."""
    written = _write_camera_calibration(
        tmp_path, monkeypatch, tmp_path / "frame.png", area="nowhere"
    )
    controller = Controller(
        ControllerSettings(
            port="/dev/null",
            baudrate=115200,
            network_id="0",
            gw_address="78",
            site=_camera_site(),
            camera_calibration=written.id8,
        )
    )
    assert controller.cameras == []


def test_a_camera_calibration_that_resolves_to_nothing_serves_no_layer(
    tmp_path, monkeypatch, serial_mock
):
    """A stale id in a config is a missing layer, never a controller that stops."""
    from dotbot.camera import registration

    monkeypatch.setattr(registration, "calibration_root", lambda: tmp_path)
    controller = Controller(
        ControllerSettings(
            port="/dev/null",
            baudrate=115200,
            network_id="0",
            gw_address="78",
            site=_camera_site(),
            camera_calibration="deadbeef",
        )
    )
    assert controller.cameras == []


# --- The camera detection log -----------------------------------------------


CAMERA_RECORD = {
    "area": "dev-corner",
    "camera_id": "22248be43bde6d93",
    "sequence": 7,
    "timestamp": 1758100000.123,
    "status": "found",
    "candidates": 1,
    "elapsed_ms": 48.2,
    "pose": {
        "centre_mm": [1523.4, 488.1],
        "photodiode_mm": [1540.2, 511.7],
        "nose_mm": [1551.0, 526.2],
        "outline_mm": [[1481.2, 500.3]],
        "heading_deg": -37.5,
        "heading_atan2_deg": 52.5,
        "green_flare": 0.82,
        "tmpl_margin": 0.91,
        "refined": True,
    },
}


def _camera_controller(tmp_path, monkeypatch, csv_output=None):
    """A controller with the camera layer served, optionally logging."""
    import cv2
    import numpy as np

    source = tmp_path / "frame.png"
    cv2.imwrite(str(source), np.full((48, 64), 180, np.uint8))
    written = _write_camera_calibration(tmp_path, monkeypatch, source)
    controller = Controller(
        ControllerSettings(
            port="/dev/null",
            baudrate=115200,
            network_id="0",
            gw_address="78",
            site=_camera_site(),
            camera_calibration=written.id8,
            csv_data_output=None if csv_output is None else str(csv_output),
        )
    )
    return controller, written


def _settled_camera_log(controller):
    """The camera stopped, so the only further rows are the test's own.

    The service hands its detector the first warp inside `start()`, and that
    detection is logged like any other, so a test that wants to read one row
    it wrote itself has to join the detector first.
    """
    for camera_service in controller.cameras:
        camera_service.stop()


def _last_row(path):
    import csv

    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))[-1]


def _bot(address, x, y, direction=315):
    return DotBotModel(
        address=address,
        application=ApplicationType.DotBot,
        swarm="0000",
        last_seen=time.time(),
        direction=direction,
        lh2_position=DotBotLH2Position(x=x, y=y),
    )


def test_a_detection_is_logged_with_the_robot_standing_in_the_area(
    tmp_path, monkeypatch, serial_mock
):
    """The row carries the lighthouse's answer for the same floor, and the count."""
    from dotbot.csv_data_logger import camera_log_path

    csv_output = tmp_path / "run.csv"
    controller, written = _camera_controller(tmp_path, monkeypatch, csv_output)
    _settled_camera_log(controller)
    assert set(controller.camera_csv_loggers) == {"dev-corner"}
    controller.dotbots = {
        "0000000000000001": _bot("0000000000000001", 1541, 509),
        "0000000000000002": _bot("0000000000000002", 100, 100),
    }
    controller._on_camera_detection(CAMERA_RECORD)
    for logger in controller.camera_csv_loggers.values():
        logger.close()

    path = camera_log_path(csv_output)
    row = _last_row(path)
    assert row["lh2_address"] == "0000000000000001"
    assert float(row["lh2_x_mm"]) == 1541
    assert row["lh2_travel_direction_deg"] == "315"
    assert row["lh2_in_area"] == "1"
    assert float(row["lh2_packet_age_s"]) >= 0
    assert row["cam_photodiode_x_mm"] == "1540.2"
    assert path.with_suffix(".toml").exists()


def test_a_detection_with_no_robot_in_the_area_still_writes_a_row(
    tmp_path, monkeypatch, serial_mock
):
    from dotbot.csv_data_logger import camera_log_path

    csv_output = tmp_path / "run.csv"
    controller, _ = _camera_controller(tmp_path, monkeypatch, csv_output)
    _settled_camera_log(controller)
    controller.dotbots = {"0000000000000002": _bot("0000000000000002", 100, 100)}
    controller._on_camera_detection(CAMERA_RECORD)
    for logger in controller.camera_csv_loggers.values():
        logger.close()

    row = _last_row(camera_log_path(csv_output))
    assert row["lh2_address"] == ""
    assert row["lh2_in_area"] == "0"
    assert row["status"] == "found"


def test_two_robots_in_the_area_log_the_nearer_one_and_say_so(
    tmp_path, monkeypatch, serial_mock
):
    """Rectangle membership, not association: the count is what filters a row."""
    from dotbot.csv_data_logger import camera_log_path

    csv_output = tmp_path / "run.csv"
    controller, _ = _camera_controller(tmp_path, monkeypatch, csv_output)
    _settled_camera_log(controller)
    controller.dotbots = {
        "0000000000000001": _bot("0000000000000001", 1900, 900),
        "0000000000000002": _bot("0000000000000002", 1530, 495),
    }
    controller._on_camera_detection(CAMERA_RECORD)
    for logger in controller.camera_csv_loggers.values():
        logger.close()

    row = _last_row(camera_log_path(csv_output))
    assert row["lh2_address"] == "0000000000000002"
    assert row["lh2_in_area"] == "2"


def test_no_csv_output_means_no_camera_log(tmp_path, monkeypatch, serial_mock):
    controller, _ = _camera_controller(tmp_path, monkeypatch, None)
    try:
        assert controller.camera_csv_loggers == {}
        controller._on_camera_detection(CAMERA_RECORD)  # a no-op, not a crash
    finally:
        for camera_service in controller.cameras:
            camera_service.stop()


def test_the_camera_s_own_first_detection_reaches_the_log(
    tmp_path, monkeypatch, serial_mock
):
    """The detector runs before `start()` returns, so the log is open first."""
    from dotbot.csv_data_logger import camera_log_path

    csv_output = tmp_path / "run.csv"
    controller, _ = _camera_controller(tmp_path, monkeypatch, csv_output)
    _settled_camera_log(controller)
    for logger in controller.camera_csv_loggers.values():
        logger.close()

    row = _last_row(camera_log_path(csv_output))
    assert row["area"] == "dev-corner"
    assert row["status"] == "none"


def test_a_log_an_old_sidecar_misdescribes_is_an_error_not_a_stop(
    tmp_path, monkeypatch, serial_mock
):
    """A refused log still leaves the camera layer served."""
    from dotbot.csv_data_logger import camera_log_path

    csv_output = tmp_path / "run.csv"
    camera_log_path(csv_output).write_text("timestamp,sequence\n")
    controller, _ = _camera_controller(tmp_path, monkeypatch, csv_output)
    try:
        assert controller.camera_csv_loggers == {}
        assert len(controller.cameras) == 1
    finally:
        for camera_service in controller.cameras:
            camera_service.stop()
