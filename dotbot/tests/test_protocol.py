import dataclasses
from dataclasses import dataclass

import pytest

from dotbot.protocol import (
    PAYLOAD_PARSERS,
    ApplicationType,
    ControlModeType,
    Frame,
    Header,
    Packet,
    PacketFieldMetadata,
    PayloadAdvertisement,
    PayloadCommandMoveRaw,
    PayloadCommandRgbLed,
    PayloadCommandXgoAction,
    PayloadControlMode,
    PayloadDotBotData,
    PayloadDotBotSimulatorData,
    PayloadGPSPosition,
    PayloadGPSWaypoints,
    PayloadLH2Location,
    PayloadLh2RawData,
    PayloadLh2RawLocation,
    PayloadLH2Waypoints,
    PayloadRawData,
    PayloadSailBotData,
    PayloadType,
    ProtocolPayloadParserException,
    register_parser,
)


@dataclass
class PayloadWithBytesTest(Packet):

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="count", disp="len."),
            PacketFieldMetadata(name="data", type_=bytes, length=0),
        ]
    )
    count: int = 0
    data: bytes = b""


@dataclass
class PayloadWithBytesFixedLengthTest(Packet):

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [
            PacketFieldMetadata(name="data", type_=bytes, length=8),
        ]
    )
    data: bytes = b""


register_parser(0x81, PayloadWithBytesTest)
register_parser(0x82, PayloadWithBytesFixedLengthTest)


@pytest.mark.parametrize(
    "bytes_,expected",
    [
        pytest.param(
            b"\x04\x02\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12",
            Header(
                version=4,
                type_=2,
                destination=0x1122221111111111,
                source=0x1212121212121212,
            ),
            id="DefaultHeader",
        ),
    ],
)
def test_parse_header(bytes_, expected):
    assert Header().from_bytes(bytes_) == expected


@pytest.mark.parametrize(
    "bytes_,header,payload_type,payload",
    [
        pytest.param(
            b"\x04\x02\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x04\x01",
            Header(
                version=4,
                type_=2,
                destination=0x1122221111111111,
                source=0x1212121212121212,
            ),
            PayloadType.ADVERTISEMENT,
            PayloadAdvertisement(application=ApplicationType.SailBot),
            id="PayloadAdvertisement",
        ),
        pytest.param(
            b"\x04\x02\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x00\x00\x42\x00\x42",
            Header(
                version=4,
                type_=2,
                destination=0x1122221111111111,
                source=0x1212121212121212,
            ),
            PayloadType.CMD_MOVE_RAW,
            PayloadCommandMoveRaw(left_x=0, left_y=66, right_x=0, right_y=66),
            id="PayloadMoveRaw",
        ),
        pytest.param(
            b"\x04\x02\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x01\x42\x42\x42",
            Header(
                version=4,
                type_=2,
                destination=0x1122221111111111,
                source=0x1212121212121212,
            ),
            PayloadType.CMD_RGB_LED,
            PayloadCommandRgbLed(red=66, green=66, blue=66),
            id="PayloadRgbLed",
        ),
        pytest.param(
            b"\x04\x02\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x0b\x01",
            Header(
                version=4,
                type_=2,
                destination=0x1122221111111111,
                source=0x1212121212121212,
            ),
            PayloadType.CMD_XGO_ACTION,
            PayloadCommandXgoAction(action=1),
            id="PayloadCommandXgoAction",
        ),
        pytest.param(
            b"\x04\x02\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x02"
            b"\x12\x34\x56\x78\x9a\xbc\xde\xf1\x01\x02",
            Header(
                version=4,
                type_=2,
                destination=0x1122221111111111,
                source=0x1212121212121212,
            ),
            PayloadType.LH2_RAW_LOCATION,
            PayloadLh2RawLocation(
                bits=0xF1DEBC9A78563412, polynomial_index=0x01, offset=0x02
            ),
            id="PayloadLH2RawLocation",
        ),
        pytest.param(
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x0d"
            b"\x02"
            b"\x12\x34\x56\x78\x9a\xbc\xde\xf1\x01\x02"
            b"\x12\x34\x56\x78\x9a\xbc\xde\xf1\x02\x04",
            Header(
                version=4,
                type_=2,
                destination=0x1122334455667788,
                source=0x1222122212221221,
            ),
            PayloadType.LH2_RAW_DATA,
            PayloadLh2RawData(
                count=2,
                locations=[
                    PayloadLh2RawLocation(
                        bits=0xF1DEBC9A78563412, polynomial_index=0x01, offset=0x02
                    ),
                    PayloadLh2RawLocation(
                        bits=0xF1DEBC9A78563412, polynomial_index=0x02, offset=0x04
                    ),
                ],
            ),
            id="PayloadLH2RawData",
        ),
        pytest.param(
            b"\x04\x02\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x03"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00",
            Header(
                version=4,
                type_=2,
                destination=0x1122221111111111,
                source=0x1212121212121212,
            ),
            PayloadType.LH2_LOCATION,
            PayloadLH2Location(pos_x=1000, pos_y=1000, pos_z=2),
            id="PayloadLH2Location",
        ),
        pytest.param(
            b"\x04\x02\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x05"
            b"&~\xe9\x02]\xe4#\x00",
            Header(
                version=4,
                type_=2,
                destination=0x1122221111111111,
                source=0x1212121212121212,
            ),
            PayloadType.GPS_POSITION,
            PayloadGPSPosition(latitude=48856614, longitude=2352221),
            id="PayloadGPSPosition",
        ),
        pytest.param(
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x0a"
            b"-\x00&~\xe9\x02]\xe4#\x00\xb4\x00\x1e\x14",
            Header(
                version=4,
                type_=2,
                destination=0x1122334455667788,
                source=0x1222122212221221,
            ),
            PayloadType.SAILBOT_DATA,
            PayloadSailBotData(
                direction=45,
                latitude=48856614,
                longitude=2352221,
                wind_angle=180,
                rudder_angle=30,
                sail_angle=20,
            ),
            id="PayloadSailbotData",
        ),
        pytest.param(
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\xfa"
            b"\x2d\x00"
            b"\x50\xc3\x00\x00"
            b"\xa8\x61\x00\x00",
            Header(
                version=4,
                type_=2,
                destination=0x1122334455667788,
                source=0x1222122212221221,
            ),
            PayloadType.DOTBOT_SIMULATOR_DATA,
            PayloadDotBotSimulatorData(theta=45, pos_x=50000, pos_y=25000),
            id="PayloadDotBotSimulatorData",
        ),
        pytest.param(
            b"\x04\x02\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x07\x01",
            Header(
                version=4,
                type_=2,
                destination=0x1122221111111111,
                source=0x1212121212121212,
            ),
            PayloadType.CONTROL_MODE,
            PayloadControlMode(mode=ControlModeType.AUTO),
            id="PayloadControlMode",
        ),
        pytest.param(
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x08"
            b"\x0a\x02"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00",
            Header(
                version=4,
                type_=2,
                destination=0x1122334455667788,
                source=0x1222122212221221,
            ),
            PayloadType.LH2_WAYPOINTS,
            PayloadLH2Waypoints(
                threshold=10,
                count=2,
                waypoints=[
                    PayloadLH2Location(pos_x=1000, pos_y=1000, pos_z=2),
                    PayloadLH2Location(pos_x=1000, pos_y=1000, pos_z=2),
                ],
            ),
            id="PayloadLH2Waypoints",
        ),
        pytest.param(
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x09"
            b"\x0a\x02"
            b"&~\xe9\x02]\xe4#\x00&~\xe9\x02]\xe4#\x00",
            Header(
                version=4,
                type_=2,
                destination=0x1122334455667788,
                source=0x1222122212221221,
            ),
            PayloadType.GPS_WAYPOINTS,
            PayloadGPSWaypoints(
                threshold=10,
                count=2,
                waypoints=[
                    PayloadGPSPosition(latitude=48856614, longitude=2352221),
                    PayloadGPSPosition(latitude=48856614, longitude=2352221),
                ],
            ),
            id="PayloadGPSWaypoints",
        ),
        pytest.param(
            b"\x01\x10\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00"  # header
            b"\x81"  # payload type
            b"\x08"  # count
            b"abcdefgh",  # data
            Header(),
            0x81,
            PayloadWithBytesTest(count=8, data=b"abcdefgh"),
            id="PayloadWithBytesTest",
        ),
        pytest.param(
            b"\x01\x10\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00"  # header
            b"\x82"  # payload type
            b"abcdefgh",  # data
            Header(),
            0x82,
            PayloadWithBytesFixedLengthTest(data=b"abcdefgh"),
            id="PayloadWithBytesFixedLengthTest",
        ),
        pytest.param(
            b"\x01\x10\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00"  # header
            b"\x10"  # Raw data type
            b"\x08"  # count
            b"abcdefgh",  # data
            Header(),
            0x10,
            PayloadRawData(count=8, data=b"abcdefgh"),
            id="PayloadRawDataTest",
        ),
    ],
)
def test_frame_parser(bytes_, header, payload_type, payload):
    frame = Frame().from_bytes(bytes_)
    assert frame.header == header
    assert frame.payload_type == payload_type
    assert frame.payload == payload


@pytest.mark.parametrize(
    "payload,expected",
    [
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                payload=PayloadCommandMoveRaw(
                    left_x=0, left_y=66, right_x=0, right_y=66
                ),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x00\x00\x42\x00\x42",
            id="PayloadMoveRaw1",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadCommandMoveRaw(left_x=0, left_y=0, right_x=0, right_y=0),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x00\x00\x00\x00\x00",
            id="PayloadMoveRaw2",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadCommandMoveRaw(left_x=-10, left_y=-10, right_x=-10, right_y=-10),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x00\xf6\xf6\xf6\xf6",
            id="PayloadMoveRaw3",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadCommandRgbLed(red=0, green=0, blue=0),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x01\x00\x00\x00",
            id="PayloadRGBLed1",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadCommandRgbLed(red=255, green=255, blue=255),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x01\xff\xff\xff",
            id="PayloadRGBLed2",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadLh2RawData(
                    count=2,
                    locations=[
                        PayloadLh2RawLocation(
                            bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                        ),
                        PayloadLh2RawLocation(
                            bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                        ),
                    ],
                ),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x0d\x02"
            b"\xf1\xde\xbc\x9a\x78\x56\x34\x12\x01\x02"
            b"\xf1\xde\xbc\x9a\x78\x56\x34\x12\x01\x02",
            id="PayloadLH2RawData",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadLH2Location(pos_x=1000, pos_y=1000, pos_z=2),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x03"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00",
            id="PayloadLH2Location",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadAdvertisement(application=ApplicationType.SailBot),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x04\x01",
            id="PayloadAdvertisement",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadGPSPosition(
                    latitude=48856614, longitude=2352221
                ),  # Paris coordinates
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x05"
            b"&~\xe9\x02]\xe4#\x00",
            id="PayloadGPSPosition",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadDotBotData(
                    direction=45,
                    count=2,
                    locations=[
                        PayloadLh2RawLocation(
                            bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                        ),
                        PayloadLh2RawLocation(
                            bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                        ),
                    ],
                ),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x06"
            b"-\x00\x02"
            b"\xf1\xde\xbc\x9a\x78\x56\x34\x12\x01\x02"
            b"\xf1\xde\xbc\x9a\x78\x56\x34\x12\x01\x02",
            id="PayloadDotBotData",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadControlMode(mode=ControlModeType.AUTO),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x07\x01",
            id="PayloadControlMode",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadLH2Waypoints(
                    threshold=10,
                    count=2,
                    waypoints=[
                        PayloadLH2Location(pos_x=1000, pos_y=1000, pos_z=2),
                        PayloadLH2Location(pos_x=1000, pos_y=1000, pos_z=2),
                    ],
                ),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x08\x0a\x02"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00",
            id="PayloadLH2Waypoints",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadGPSWaypoints(
                    threshold=10,
                    count=2,
                    waypoints=[
                        PayloadGPSPosition(latitude=48856614, longitude=2352221),
                        PayloadGPSPosition(latitude=48856614, longitude=2352221),
                    ],
                ),  # Paris coordinates x 2
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x09\x0a\x02"
            b"&~\xe9\x02]\xe4#\x00&~\xe9\x02]\xe4#\x00",
            id="PayloadGPSWaypoints",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadSailBotData(
                    direction=45,
                    latitude=48856614,
                    longitude=2352221,
                    wind_angle=180,
                    rudder_angle=30,
                    sail_angle=20,
                ),  # Paris coordinates
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x0a"
            b"-\x00&~\xe9\x02]\xe4#\x00\xb4\x00\x1e\x14",
            id="PayloadSailBotData",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadDotBotSimulatorData(
                    theta=45,
                    pos_x=50000,
                    pos_y=25000,
                ),
            ),
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\xfa"
            b"\x2d\x00"
            b"\x50\xc3\x00\x00"
            b"\xa8\x61\x00\x00",
            id="PayloadDotBotSimulatorData",
        ),
        pytest.param(
            Frame(
                header=Header(), payload=PayloadWithBytesTest(count=8, data=b"abcdefgh")
            ),
            b"\x01\x10\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00"  # header
            b"\x81"  # payload type
            b"\x08"  # count
            b"abcdefgh",  # data
            id="PayloadWithBytesTest",
        ),
        pytest.param(
            Frame(
                header=Header(),
                payload=PayloadWithBytesFixedLengthTest(data=b"abcdefgh"),
            ),
            b"\x01\x10\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00"  # header
            b"\x82"  # payload type
            b"abcdefgh",  # data
            id="PayloadWithBytesFixedLengthTest",
        ),
        pytest.param(
            Frame(
                header=Header(),
                payload=PayloadRawData(count=8, data=b"abcdefgh"),
            ),
            b"\x01\x10\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00"  # header
            b"\x10"  # Raw data type
            b"\x08"  # count
            b"abcdefgh",  # data
            id="PayloadRawDataTest",
        ),
    ],
)
def test_payload_to_bytes(payload, expected):
    result = payload.to_bytes()
    assert result == expected, f"{result} != {expected}"


@pytest.mark.parametrize(
    "payload,string",
    [
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadCommandMoveRaw(left_x=0, left_y=66, right_x=0, right_y=66),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+------+------+------+------+\n"
                " CMD_MOVE_RAW    | ver. | type | dst                | src                | type | lx   | ly   | rx   | ry   |\n"
                " (23 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x00 | 0x00 | 0x42 | 0x00 | 0x42 |\n"
                "                 +------+------+--------------------+--------------------+------+------+------+------+------+\n"
                "\n"
            ),
            id="MoveRaw",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadCommandRgbLed(red=0, green=0, blue=0),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+------+------+------+\n"
                " CMD_RGB_LED     | ver. | type | dst                | src                | type | red  | green| blue |\n"
                " (22 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x01 | 0x00 | 0x00 | 0x00 |\n"
                "                 +------+------+--------------------+--------------------+------+------+------+------+\n"
                "\n"
            ),
            id="RGBLed",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadLh2RawData(
                    count=2,
                    locations=[
                        PayloadLh2RawLocation(
                            bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                        ),
                        PayloadLh2RawLocation(
                            bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                        ),
                    ],
                ),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " LH2_RAW_DATA    | ver. | type | dst                | src                | type |\n"
                " (40 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x0d |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +------+--------------------+------+------+--------------------+------+------+\n"
                "                 | len  | bits               | poly | off. | bits               | poly | off. |\n"
                "                 | 0x02 | 0x123456789abcdef1 | 0x01 | 0x02 | 0x123456789abcdef1 | 0x01 | 0x02 |\n"
                "                 +------+--------------------+------+------+--------------------+------+------+\n"
                "\n"
            ),
            id="LH2RawData",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadLH2Location(pos_x=1000, pos_y=1000, pos_z=2),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " LH2_LOCATION    | ver. | type | dst                | src                | type |\n"
                " (31 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x03 |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +------------+------------+------------+\n"
                "                 | x          | y          | z          |\n"
                "                 | 0x000003e8 | 0x000003e8 | 0x00000002 |\n"
                "                 +------------+------------+------------+\n"
                "\n"
            ),
            id="LH2Location",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadAdvertisement(application=ApplicationType.SailBot),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+------+\n"
                " ADVERTISEMENT   | ver. | type | dst                | src                | type | app  |\n"
                " (20 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x04 | 0x01 |\n"
                "                 +------+------+--------------------+--------------------+------+------+\n"
                "\n"
            ),
            id="Advertisement",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadGPSPosition(
                    latitude=48856614, longitude=2352221
                ),  # Paris coordinates
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " GPS_POSITION    | ver. | type | dst                | src                | type |\n"
                " (27 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x05 |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +------------+------------+\n"
                "                 | lat.       | long.      |\n"
                "                 | 0x02e97e26 | 0x0023e45d |\n"
                "                 +------------+------------+\n"
                "\n"
            ),
            id="GPSPosition",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadDotBotData(
                    direction=45,
                    count=2,
                    locations=[
                        PayloadLh2RawLocation(
                            bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                        ),
                        PayloadLh2RawLocation(
                            bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                        ),
                    ],
                ),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " DOTBOT_DATA     | ver. | type | dst                | src                | type |\n"
                " (42 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x06 |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +--------+------+--------------------+------+------+--------------------+------+------+\n"
                "                 | dir.   | len  | bits               | poly | off. | bits               | poly | off. |\n"
                "                 | 0x002d | 0x02 | 0x123456789abcdef1 | 0x01 | 0x02 | 0x123456789abcdef1 | 0x01 | 0x02 |\n"
                "                 +--------+------+--------------------+------+------+--------------------+------+------+\n"
                "\n"
            ),
            id="DotBotData",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadControlMode(mode=1),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+------+\n"
                " CONTROL_MODE    | ver. | type | dst                | src                | type | mode |\n"
                " (20 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x07 | 0x01 |\n"
                "                 +------+------+--------------------+--------------------+------+------+\n"
                "\n"
            ),
            id="ControlMode",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadLH2Waypoints(
                    threshold=10,
                    count=2,
                    waypoints=[
                        PayloadLH2Location(pos_x=1000, pos_y=1000, pos_z=2),
                        PayloadLH2Location(pos_x=1000, pos_y=1000, pos_z=2),
                    ],
                ),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " LH2_WAYPOINTS   | ver. | type | dst                | src                | type |\n"
                " (45 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x08 |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +------+------+------------+------------+------------+------------+------------+------------+\n"
                "                 | thr. | len. | x          | y          | z          | x          | y          | z          |\n"
                "                 | 0x0a | 0x02 | 0x000003e8 | 0x000003e8 | 0x00000002 | 0x000003e8 | 0x000003e8 | 0x00000002 |\n"
                "                 +------+------+------------+------------+------------+------------+------------+------------+\n"
                "\n"
            ),
            id="LH2Waypoints",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadGPSWaypoints(
                    threshold=10,
                    count=2,
                    waypoints=[
                        PayloadGPSPosition(latitude=48856614, longitude=2352221),
                        PayloadGPSPosition(latitude=48856614, longitude=2352221),
                    ],
                ),  # Paris coordinates x 2
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " GPS_WAYPOINTS   | ver. | type | dst                | src                | type |\n"
                " (37 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x09 |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +------+------+------------+------------+------------+------------+\n"
                "                 | thr. | len. | lat.       | long.      | lat.       | long.      |\n"
                "                 | 0x0a | 0x02 | 0x02e97e26 | 0x0023e45d | 0x02e97e26 | 0x0023e45d |\n"
                "                 +------+------+------------+------------+------------+------------+\n"
                "\n"
            ),
            id="GPSWaypoints",
        ),
        pytest.param(
            Frame(
                Header(
                    version=4,
                    type_=2,
                    destination=0x1122334455667788,
                    source=0x1222122212221221,
                ),
                PayloadSailBotData(
                    direction=45, latitude=48856614, longitude=2352221
                ),  # Paris coordinates
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " SAILBOT_DATA    | ver. | type | dst                | src                | type |\n"
                " (33 Bytes)      | 0x04 | 0x02 | 0x1122334455667788 | 0x1222122212221221 | 0x0a |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +--------+------------+------------+--------+------+------+\n"
                "                 | dir.   | lat.       | long.      | wind   | rud. | sail.|\n"
                "                 | 0x002d | 0x02e97e26 | 0x0023e45d | 0xffff | 0x00 | 0x00 |\n"
                "                 +--------+------------+------------+--------+------+------+\n"
                "\n"
            ),
            id="SailBotData",
        ),
        pytest.param(
            Frame(
                header=Header(),
                payload=PayloadWithBytesTest(count=8, data=b"abcdefgh"),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " CUSTOM_DATA     | ver. | type | dst                | src                | type |\n"
                " (28 Bytes)      | 0x01 | 0x10 | 0xffffffffffffffff | 0x0000000000000000 | 0x81 |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +------+--------------------+\n"
                "                 | len. | data               |\n"
                "                 | 0x08 | 0x6162636465666768 |\n"
                "                 +------+--------------------+\n"
                "\n"
            ),
            id="PayloadWithBytesTest",
        ),
        pytest.param(
            Frame(
                header=Header(),
                payload=PayloadWithBytesFixedLengthTest(data=b"abcdefgh"),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " CUSTOM_DATA     | ver. | type | dst                | src                | type |\n"
                " (27 Bytes)      | 0x01 | 0x10 | 0xffffffffffffffff | 0x0000000000000000 | 0x82 |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +--------------------+\n"
                "                 | data               |\n"
                "                 | 0x6162636465666768 |\n"
                "                 +--------------------+\n"
                "\n"
            ),
            id="PayloadWithBytesFixedLengthTest",
        ),
        pytest.param(
            Frame(
                header=Header(),
                payload=PayloadRawData(count=8, data=b"abcdefgh"),
            ),
            (
                "                 +------+------+--------------------+--------------------+------+\n"
                " RAW_DATA        | ver. | type | dst                | src                | type |\n"
                " (28 Bytes)      | 0x01 | 0x10 | 0xffffffffffffffff | 0x0000000000000000 | 0x10 |\n"
                "                 +------+------+--------------------+--------------------+------+\n"
                "                 +------+--------------------+\n"
                "                 | len. | data               |\n"
                "                 | 0x08 | 0x6162636465666768 |\n"
                "                 +------+--------------------+\n"
                "\n"
            ),
            id="PayloadRawDataTest",
        ),
    ],
)
def test_payload_frame_repr(payload, string, capsys):
    print(payload)
    out, _ = capsys.readouterr()
    assert out == string


def test_parse_missing_metadata():

    @dataclass
    class PayloadMissingMetadata(Packet):

        field: int = 0

    with pytest.raises(ValueError) as excinfo:
        PayloadMissingMetadata().from_bytes(b"")
    assert str(excinfo.value) == "metadata must be defined first"


@pytest.mark.parametrize(
    "packet,bytes_",
    [
        pytest.param(
            PayloadAdvertisement(application=ApplicationType.DotBot),
            b"",
            id="PayloadAdvertisement",
        ),
        pytest.param(
            PayloadDotBotData(
                direction=45,
                count=2,
                locations=[
                    PayloadLh2RawLocation(
                        bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                    ),
                    PayloadLh2RawLocation(
                        bits=0x123456789ABCDEF1, polynomial_index=0x01, offset=0x02
                    ),
                ],
            ),
            b"-\x00\x02" b"\xf1\xde\xbc\x9a\x78\x56\x34\x12\x01\x02",
            id="PayloadLh2RawLocation",
        ),
    ],
)
def test_from_bytes_empty(packet, bytes_):
    with pytest.raises(ValueError) as excinfo:
        packet.from_bytes(bytes_)
    assert str(excinfo.value) == "Not enough bytes to parse"


@dataclass
class PayloadTest(Packet):

    metadata: list[PacketFieldMetadata] = dataclasses.field(
        default_factory=lambda: [PacketFieldMetadata(name="field", type_=int)]
    )
    field: int = 0


@pytest.mark.parametrize(
    "payload_type,value_str",
    [
        (0x01, "0x01"),
        (0x0A, "0x0A"),
        (0xFA, "0xFA"),
    ],
)
def test_register_already_registered(payload_type, value_str):
    with pytest.raises(ValueError) as excinfo:
        register_parser(payload_type, PayloadTest)
    assert str(excinfo.value) == f"Payload type '{value_str}' already registered"


def test_register_reserved():
    with pytest.raises(ValueError) as excinfo:
        register_parser(0x7A, PayloadTest)
    assert str(excinfo.value) == "Payload type '0x7A' is reserved"


def test_register_parser():
    register_parser(0xFE, PayloadTest)
    assert PAYLOAD_PARSERS[0xFE] == PayloadTest


def test_parse_non_registered_payload():
    with pytest.raises(ProtocolPayloadParserException) as excinfo:
        Frame().from_bytes(
            b"\x04\x02\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\xfd\x01"
        )
    assert str(excinfo.value).startswith("Unsupported payload type")

    @dataclass
    class PayloadNotRegisteredTest(Packet):

        metadata: list[PacketFieldMetadata] = dataclasses.field(
            default_factory=lambda: [PacketFieldMetadata(name="field", type_=int)]
        )
        field: int = 0

    frame = Frame(header=Header(), payload=PayloadNotRegisteredTest())
    with pytest.raises(ValueError) as excinfo:
        frame.payload_type
    assert str(excinfo.value).startswith("Unsupported payload class")
