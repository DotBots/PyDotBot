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


def test_controller_loads_the_calibration_named_by_id(tmp_path, monkeypatch, serial_mock):
    """An id prefix resolves under calibrations/<site>/, never the newest file."""
    import numpy as np

    from dotbot.calibration.wire import unpack_payload
    from dotbot.controller import load_calibration

    written = _write_calibration(tmp_path, monkeypatch)
    settings = ControllerSettings(
        port="/dev/null", baudrate=115200, network_id="0", gw_address="78",
        site=Site(name="site-a"), calibration=written.id8,
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

    from dotbot.calibration.lighthouse2 import homography_as_bytes

    pushed = bytes([len(controller.lh2_calibration)]) + b"".join(
        homography_as_bytes(s.matrix) for s in controller.lh2_calibration
    )
    # The int32 shim quantises each element to a thousandth.
    assert np.allclose(
        [
            [v / 1e3 for v in row]
            for row in [
                [
                    int.from_bytes(pushed[1 + i * 4 : 5 + i * 4], "little", signed=True)
                    for i in range(9)
                ][j : j + 3]
                for j in (0, 3, 6)
            ]
        ],
        written.stations[0].homography,
        atol=1e-3,
    )
    assert len(unpack_payload(bytes([1]) + b"\x00" * 36)) == 1


def test_controller_with_no_calibration_loads_nothing(serial_mock):
    """No --calibration and no config key: nothing is loaded, and it is said."""
    settings = ControllerSettings(
        port="/dev/null", baudrate=115200, network_id="0", gw_address="78"
    )
    controller = Controller(settings)
    assert controller.lh2_calibration == []
    assert controller.calibration is None


def test_a_controller_keeps_the_site_it_was_given(serial_mock):
    settings = ControllerSettings(
        port="/dev/null", baudrate=115200, network_id="0", gw_address="78",
        site=C405,
    )
    controller = Controller(settings)
    assert controller.site.name == "c405-arena"
    assert sorted(controller.site.areas) == ["annex", "wing"]


def test_a_controller_with_no_site_keeps_the_neutral_one(serial_mock):
    settings = ControllerSettings(
        port="/dev/null", baudrate=115200, network_id="0", gw_address="78",
    )
    controller = Controller(settings)
    assert controller.site.name == "default"
    assert controller.site.areas == {}
