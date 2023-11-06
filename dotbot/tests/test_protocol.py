import pytest

from dotbot.protocol import (
    PROTOCOL_VERSION,
    Advertisement,
    CommandMoveRaw,
    CommandRgbLed,
    ControlMode,
    ControlModeType,
    DotBotData,
    GPSPosition,
    GPSWaypoints,
    LH2Location,
    Lh2RawData,
    Lh2RawLocation,
    LH2Waypoints,
    PayloadType,
    ProtocolHeader,
    ProtocolPayload,
    ProtocolPayloadParserException,
    SailBotData,
)


@pytest.mark.parametrize(
    "payload,expected",
    [
        pytest.param(
            b"\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x34\x12\x00\x08\x00\x00\x00\x00\x00\x00\x42\x00\x42",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122221111111111,
                    0x1212121212121212,
                    0x1234,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.CMD_MOVE_RAW,
                CommandMoveRaw(0, 66, 0, 66),
            ),
            id="MoveRaw",
        ),
        pytest.param(
            b"\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x34\x12\x00\x08\x00\x00\x00\x00\x01\x42\x42\x42",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122221111111111,
                    0x1212121212121212,
                    0x1234,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.CMD_RGB_LED,
                CommandRgbLed(66, 66, 66),
            ),
            id="RGBLed",
        ),
        pytest.param(
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x08\x00\x00\x00\x00\x02"
            b"\x12\x34\x56\x78\x9a\xbc\xde\xf1\x01\x02"
            b"\x12\x34\x56\x78\x9a\xbc\xde\xf1\x01\x02",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122334455667788,
                    0x1222122212221221,
                    0x1442,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.LH2_RAW_DATA,
                Lh2RawData(
                    [
                        Lh2RawLocation(0xF1DEBC9A78563412, 0x01, 0x02),
                        Lh2RawLocation(0xF1DEBC9A78563412, 0x01, 0x02),
                    ],
                ),
            ),
            id="LH2RawData",
        ),
        pytest.param(
            b"\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x34\x12\x00\x08\x00\x00\x00\x00\x03"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122221111111111,
                    0x1212121212121212,
                    0x1234,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.LH2_LOCATION,
                LH2Location(1000, 1000, 2),
            ),
            id="LH2Location",
        ),
        pytest.param(
            b"\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x34\x12\x00\x08\x00\x00\x00\x00\x04",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122221111111111,
                    0x1212121212121212,
                    0x1234,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.ADVERTISEMENT,
                Advertisement(),
            ),
            id="Advertisement",
        ),
        pytest.param(
            b"\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x34\x12\x00\x08\x00\x00\x00\x00\x05"
            b"&~\xe9\x02]\xe4#\x00",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122221111111111,
                    0x1212121212121212,
                    0x1234,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.GPS_POSITION,
                GPSPosition(48856614, 2352221),  # Paris coordinates
            ),
            id="GPSPosition",
        ),
        pytest.param(
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x08\x00\x00\x00\x00\x06"
            b"-\x00"
            b"\x12\x34\x56\x78\x9a\xbc\xde\xf1\x01\x02"
            b"\x12\x34\x56\x78\x9a\xbc\xde\xf1\x01\x02",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122334455667788,
                    0x1222122212221221,
                    0x1442,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.DOTBOT_DATA,
                DotBotData(
                    direction=45,
                    locations=[
                        Lh2RawLocation(0xF1DEBC9A78563412, 0x01, 0x02),
                        Lh2RawLocation(0xF1DEBC9A78563412, 0x01, 0x02),
                    ],
                ),
            ),
            id="DotBotData",
        ),
        pytest.param(
            b"\x11\x11\x11\x11\x11\x22\x22\x11\x12\x12\x12\x12\x12\x12\x12\x12\x34\x12\x00\x08\x00\x00\x00\x00\x07\x01",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122221111111111,
                    0x1212121212121212,
                    0x1234,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.CONTROL_MODE,
                ControlMode(ControlModeType.AUTO),
            ),
            id="ControlMode",
        ),
        pytest.param(
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x08\x00\x00\x00\x00\x08\x02\x0a"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122334455667788,
                    0x1222122212221221,
                    0x1442,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.LH2_WAYPOINTS,
                LH2Waypoints(threshold=0, waypoints=[]),
            ),
            id="LH2Waypoints",
        ),
        pytest.param(
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x08\x00\x00\x00\x00\x09\x02\x0a"
            b"&~\xe9\x02]\xe4#\x00&~\xe9\x02]\xe4#\x00",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122334455667788,
                    0x1222122212221221,
                    0x1442,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.GPS_WAYPOINTS,
                GPSWaypoints(threshold=0, waypoints=[]),
            ),
            id="GPSWaypoints",
        ),
        pytest.param(
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x08\x00\x00\x00\x00\x0a"
            b"-\x00&~\xe9\x02]\xe4#\x00",
            ProtocolPayload(
                ProtocolHeader(
                    0x1122334455667788,
                    0x1222122212221221,
                    0x1442,
                    0,
                    PROTOCOL_VERSION,
                    0,
                ),
                PayloadType.SAILBOT_DATA,
                SailBotData(direction=45, latitude=48856614, longitude=2352221),
            ),
            id="SailBotData",
        ),
        pytest.param(
            b"\x11\x22\x22\x11\x11\x11\x11\x11\x12\x12\x12\x12\x12\x12\x12\x12\x00\x00\x00\x08\x00\x00\x00\x00\xff",
            ValueError("255 is not a valid PayloadType"),
            id="invalid payload",
        ),
        pytest.param(
            b"\x11\x22\x22\x11\x11\x11\x11\x11\x12\x12\x12\x12\x12\x12\x12\x12\x00\x00\x00\x08\x00\x00\x00\x00\x0b",
            ProtocolPayloadParserException("Unsupported payload type '11'"),
            id="unsupported payload type",
        ),
        pytest.param(
            b"\x11\x22\x22\x11\x11\x11\x11\x11\x12\x12\x12\x12\x12\x12\x12\x12\x00\x00\x00\x03\x00\x00\x00\x00\x0a",
            ProtocolPayloadParserException(
                f"Invalid header: Unsupported payload version '3' (expected: {PROTOCOL_VERSION})"
            ),
            id="unsupported protocol version",
        ),
        pytest.param(
            b"\x11\x22\x22\x11\x11\x11\x11\x11\x12\x12\x12\x12\x12\x12\x12\x12\x00\x00\xff\x08\x00\x00\x00\x00\x0a",
            ProtocolPayloadParserException(
                "Invalid header: 255 is not a valid ApplicationType"
            ),
            id="Invalid application type",
        ),
    ],
)
def test_protocol_parser(payload, expected):
    if isinstance(expected, Exception):
        with pytest.raises(expected.__class__) as exc_info:
            _ = ProtocolPayload.from_bytes(payload)
        assert str(exc_info.value) == str(expected)
    else:
        protocol = ProtocolPayload.from_bytes(payload)
        assert protocol.header == expected.header
        assert protocol.payload_type == expected.payload_type
        assert protocol.values == expected.values


@pytest.mark.parametrize(
    "payload,expected",
    [
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.CMD_MOVE_RAW,
                CommandMoveRaw(0, 66, 0, 66),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x00\x00\x42\x00\x42",
            id="MoveRaw1",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.CMD_MOVE_RAW,
                CommandMoveRaw(0, 0, 0, 0),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00",
            id="MoveRaw2",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.CMD_MOVE_RAW,
                CommandMoveRaw(-10, -10, -10, -10),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x00\xf6\xf6\xf6\xf6",
            id="MoveRaw3",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.CMD_RGB_LED,
                CommandRgbLed(0, 0, 0),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x01\x00\x00\x00",
            id="RGBLed1",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.CMD_RGB_LED,
                CommandRgbLed(255, 255, 255),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x01\xff\xff\xff",
            id="RGBLed2",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.LH2_RAW_DATA,
                Lh2RawData(
                    [
                        Lh2RawLocation(0x123456789ABCDEF1, 0x01, 0x02),
                        Lh2RawLocation(0x123456789ABCDEF1, 0x01, 0x02),
                    ],
                ),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x02"
            b"\xf1\xde\xbc\x9a\x78\x56\x34\x12\x01\x02"
            b"\xf1\xde\xbc\x9a\x78\x56\x34\x12\x01\x02",
            id="LH2RawData",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.LH2_LOCATION,
                LH2Location(1000, 1000, 2),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x03"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00",
            id="LH2Location",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.ADVERTISEMENT,
                Advertisement(),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x04",
            id="Advertisement",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.GPS_POSITION,
                GPSPosition(48856614, 2352221),  # Paris coordinates
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x05"
            b"&~\xe9\x02]\xe4#\x00",
            id="GPSPosition",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.DOTBOT_DATA,
                DotBotData(
                    direction=45,
                    locations=[
                        Lh2RawLocation(0x123456789ABCDEF1, 0x01, 0x02),
                        Lh2RawLocation(0x123456789ABCDEF1, 0x01, 0x02),
                    ],
                ),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x06"
            b"-\x00"
            b"\xf1\xde\xbc\x9a\x78\x56\x34\x12\x01\x02"
            b"\xf1\xde\xbc\x9a\x78\x56\x34\x12\x01\x02",
            id="DotBotData",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.CONTROL_MODE,
                ControlMode(ControlModeType.AUTO),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x07\x01",
            id="ControlMode",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.LH2_WAYPOINTS,
                LH2Waypoints(
                    threshold=10,
                    waypoints=[LH2Location(1000, 1000, 2), LH2Location(1000, 1000, 2)],
                ),
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x08\x02\x0a"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00"
            b"\xe8\x03\x00\x00\xe8\x03\x00\x00\x02\x00\x00\x00",
            id="LH2Waypoints",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.GPS_WAYPOINTS,
                GPSWaypoints(
                    threshold=10,
                    waypoints=[
                        GPSPosition(48856614, 2352221),
                        GPSPosition(48856614, 2352221),
                    ],
                ),  # Paris coordinates x 2
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x09\x02\x0a"
            b"&~\xe9\x02]\xe4#\x00&~\xe9\x02]\xe4#\x00",
            id="GPSWaypoints",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x1442, 0, 1, 0),
                PayloadType.SAILBOT_DATA,
                SailBotData(
                    direction=45, latitude=48856614, longitude=2352221
                ),  # Paris coordinates
            ),
            b"\x88\x77\x66\x55\x44\x33\x22\x11\x21\x12\x22\x12\x22\x12\x22\x12\x42\x14\x00\x01\x00\x00\x00\x00\x0a"
            b"-\x00&~\xe9\x02]\xe4#\x00",
            id="SailBotData",
        ),
    ],
)
def test_payload(payload, expected):
    result = payload.to_bytes()
    assert result == expected, f"{result} != {expected}"


@pytest.mark.parametrize(
    "payload,string",
    [
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.CMD_MOVE_RAW,
                CommandMoveRaw(0, 66, 0, 66),
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+------+------+------+------+\n"
                " CMD_MOVE_RAW    | dst                              | src                              | swarm id | app. | ver. | msg id           | type | lx   | ly   | rx   | ry   |\n"
                " (29 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x00 | 0x00 | 0x42 | 0x00 | 0x42 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+------+------+------+------+\n"
                "\n"
            ),
            id="MoveRaw",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.CMD_RGB_LED,
                CommandRgbLed(0, 0, 0),
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+------+------+------+\n"
                " CMD_RGB_LED     | dst                              | src                              | swarm id | app. | ver. | msg id           | type | red  | green| blue |\n"
                " (28 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x01 | 0x00 | 0x00 | 0x00 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+------+------+------+\n"
                "\n"
            ),
            id="RGBLed",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.LH2_RAW_DATA,
                Lh2RawData(
                    [
                        Lh2RawLocation(0x123456789ABCDEF1, 0x01, 0x02),
                        Lh2RawLocation(0x123456789ABCDEF1, 0x01, 0x02),
                    ],
                ),
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                " LH2_RAW_DATA    | dst                              | src                              | swarm id | app. | ver. | msg id           | type |\n"
                " (45 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x02 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                "                 +----------------------------------+------+------+----------------------------------+------+------+\n"
                "                 | bits                             | poly | off. | bits                             | poly | off. |\n"
                "                 | 0x123456789abcdef1               | 0x01 | 0x02 | 0x123456789abcdef1               | 0x01 | 0x02 |\n"
                "                 +----------------------------------+------+------+----------------------------------+------+------+\n"
                "\n"
            ),
            id="LH2RawData",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.LH2_LOCATION,
                LH2Location(1000, 1000, 2),
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                " LH2_LOCATION    | dst                              | src                              | swarm id | app. | ver. | msg id           | type |\n"
                " (37 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x03 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                "                 +------------------+------------------+------------------+\n"
                "                 | x                | y                | z                |\n"
                "                 | 0x000003e8       | 0x000003e8       | 0x00000002       |\n"
                "                 +------------------+------------------+------------------+\n"
                "\n"
            ),
            id="LH2Location",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.ADVERTISEMENT,
                Advertisement(),
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                " ADVERTISEMENT   | dst                              | src                              | swarm id | app. | ver. | msg id           | type |\n"
                " (25 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x04 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                "\n"
            ),
            id="Advertisement",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.GPS_POSITION,
                GPSPosition(48856614, 2352221),  # Paris coordinates
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                " GPS_POSITION    | dst                              | src                              | swarm id | app. | ver. | msg id           | type |\n"
                " (33 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x05 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                "                 +------------------+------------------+\n"
                "                 | latitude         | longitude        |\n"
                "                 | 0x02e97e26       | 0x0023e45d       |\n"
                "                 +------------------+------------------+\n"
                "\n"
            ),
            id="GPSPosition",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.DOTBOT_DATA,
                DotBotData(
                    direction=45,
                    locations=[
                        Lh2RawLocation(0x123456789ABCDEF1, 0x01, 0x02),
                        Lh2RawLocation(0x123456789ABCDEF1, 0x01, 0x02),
                    ],
                ),
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                " DOTBOT_DATA     | dst                              | src                              | swarm id | app. | ver. | msg id           | type |\n"
                " (47 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x06 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                "                 +----------+----------------------------------+------+------+----------------------------------+------+------+\n"
                "                 | dir.     | bits                             | poly | off. | bits                             | poly | off. |\n"
                "                 | 0x002d   | 0x123456789abcdef1               | 0x01 | 0x02 | 0x123456789abcdef1               | 0x01 | 0x02 |\n"
                "                 +----------+----------------------------------+------+------+----------------------------------+------+------+\n"
                "\n"
            ),
            id="DotBotData",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.CONTROL_MODE,
                ControlMode(1),
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+------+\n"
                " CONTROL_MODE    | dst                              | src                              | swarm id | app. | ver. | msg id           | type | mode |\n"
                " (26 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x07 | 0x01 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+------+\n"
                "\n"
            ),
            id="ControlMode",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.LH2_WAYPOINTS,
                LH2Waypoints(
                    threshold=10,
                    waypoints=[LH2Location(1000, 1000, 2), LH2Location(1000, 1000, 2)],
                ),
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                " LH2_WAYPOINTS   | dst                              | src                              | swarm id | app. | ver. | msg id           | type |\n"
                " (51 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x08 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                "                 +------+------+------------------+------------------+------------------+------------------+------------------+------------------+\n"
                "                 | len. | thr. | x                | y                | z                | x                | y                | z                |\n"
                "                 | 0x02 | 0x0a | 0x000003e8       | 0x000003e8       | 0x00000002       | 0x000003e8       | 0x000003e8       | 0x00000002       |\n"
                "                 +------+------+------------------+------------------+------------------+------------------+------------------+------------------+\n"
                "\n"
            ),
            id="LH2Waypoints",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.GPS_WAYPOINTS,
                GPSWaypoints(
                    threshold=10,
                    waypoints=[
                        GPSPosition(48856614, 2352221),
                        GPSPosition(48856614, 2352221),
                    ],
                ),  # Paris coordinates x 2
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                " GPS_WAYPOINTS   | dst                              | src                              | swarm id | app. | ver. | msg id           | type |\n"
                " (43 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x09 |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                "                 +------+------+------------------+------------------+------------------+------------------+\n"
                "                 | len. | thr. | latitude         | longitude        | latitude         | longitude        |\n"
                "                 | 0x02 | 0x0a | 0x02e97e26       | 0x0023e45d       | 0x02e97e26       | 0x0023e45d       |\n"
                "                 +------+------+------------------+------------------+------------------+------------------+\n"
                "\n"
            ),
            id="GPSWaypoints",
        ),
        pytest.param(
            ProtocolPayload(
                ProtocolHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 0, 1, 0),
                PayloadType.SAILBOT_DATA,
                SailBotData(
                    direction=45, latitude=48856614, longitude=2352221
                ),  # Paris coordinates
            ),
            (
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                " SAILBOT_DATA    | dst                              | src                              | swarm id | app. | ver. | msg id           | type |\n"
                " (35 Bytes)      | 0x1122334455667788               | 0x1222122212221221               | 0x2442   | 0x00 | 0x01 | 0x00000000       | 0x0a |\n"
                "                 +----------------------------------+----------------------------------+----------+------+------+------------------+------+\n"
                "                 +----------+------------------+------------------+\n"
                "                 | dir.     | latitude         | longitude        |\n"
                "                 | 0x002d   | 0x02e97e26       | 0x0023e45d       |\n"
                "                 +----------+------------------+------------------+\n"
                "\n"
            ),
            id="SailBotData",
        ),
    ],
)
def test_payload_repr(payload, string, capsys):
    print(payload)
    out, _ = capsys.readouterr()
    assert out == string
