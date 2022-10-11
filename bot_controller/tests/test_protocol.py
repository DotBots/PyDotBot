import pytest


from bot_controller.protocol import (
    ProtocolPayloadParserException,
    ProtocolPayloadHeader,
    ProtocolCommandMoveRaw,
    ProtocolCommandRgbLed,
    parse_payload,
)


@pytest.mark.parametrize(
    "payload,expected",
    [
        pytest.param(
            b"\x11\x22\x22\x11\x11\x11\x11\x11\x12\x12\x12\x12\x12\x12\x12\x12\x12\x34\x01\x00\x00\x42\x00\x42",
            ProtocolCommandMoveRaw(
                ProtocolPayloadHeader(
                    0x1122221111111111, 0x1212121212121212, 0x1234, 1
                ),
                0,
                66,
                0,
                66,
            ),
            id="MoveRaw",
        ),
        pytest.param(
            b"\x11\x22\x22\x11\x11\x11\x11\x11\x12\x12\x12\x12\x12\x12\x12\x12\x12\x34\x01\x01\x42\x42\x42",
            ProtocolCommandRgbLed(
                ProtocolPayloadHeader(
                    0x1122221111111111, 0x1212121212121212, 0x1234, 1
                ),
                66,
                66,
                66,
            ),
            id="RGBLed",
        ),
        pytest.param(
            b"\x11\x22\x22\x11\x11\x11\x11\x11\x12\x12\x12\x12\x12\x12\x12\x12\x00\x00\x01\x04",
            ValueError(),
            id="invalid payload",
        ),
        pytest.param(
            b"\x11\x22\x22\x11\x11\x11\x11\x11\x12\x12\x12\x12\x12\x12\x12\x12\x00\x00\x01\x03",
            ProtocolPayloadParserException(),
            id="unsupported payload type",
        ),
    ],
)
def test_parse_payload(payload, expected):
    if isinstance(expected, Exception):
        with pytest.raises(expected.__class__):
            _ = parse_payload(payload)
    else:
        result = parse_payload(payload)
        assert result == expected


@pytest.mark.parametrize(
    "payload,expected",
    [
        pytest.param(
            ProtocolPayloadHeader(0xFFFFFFFFFFFFFFFF, 0x0000000000000000, 0x1234, 0),
            b"\xff\xff\xff\xff\xff\xff\xff\xff\x00\x00\x00\x00\x00\x00\x00\x00\x12\x34\x00",
            id="header 1",
        ),
        pytest.param(
            ProtocolPayloadHeader(0x1111111111111111, 0x1212121212121212, 0x0000, 1),
            b"\x11\x11\x11\x11\x11\x11\x11\x11\x12\x12\x12\x12\x12\x12\x12\x12\x00\x00\x01",
            id="header 2",
        ),
        pytest.param(
            ProtocolPayloadHeader(0x1122334455667788, 0x1222122212221221, 0x2442, 1),
            b"\x11\x22\x33\x44\x55\x66\x77\x88\x12\x22\x12\x22\x12\x22\x12\x21\x24\x42\x01",
            id="header 3",
        ),
        pytest.param(
            ProtocolCommandMoveRaw(
                ProtocolPayloadHeader(
                    0x1122334455667788, 0x1222122212221221, 0x2442, 1
                ),
                0,
                66,
                0,
                66,
            ),
            b"\x11\x22\x33\x44\x55\x66\x77\x88\x12\x22\x12\x22\x12\x22\x12\x21\x24\x42\x01\x00\x00\x42\x00\x42",
            id="move raw 1",
        ),
        pytest.param(
            ProtocolCommandMoveRaw(
                ProtocolPayloadHeader(
                    0x1122334455667788, 0x1222122212221221, 0x2442, 1
                ),
                0,
                0,
                0,
                0,
            ),
            b"\x11\x22\x33\x44\x55\x66\x77\x88\x12\x22\x12\x22\x12\x22\x12\x21\x24\x42\x01\x00\x00\x00\x00\x00",
            id="move raw 2",
        ),
        pytest.param(
            ProtocolCommandMoveRaw(
                ProtocolPayloadHeader(
                    0x1122334455667788, 0x1222122212221221, 0x2442, 1
                ),
                -10,
                -10,
                -10,
                -10,
            ),
            b"\x11\x22\x33\x44\x55\x66\x77\x88\x12\x22\x12\x22\x12\x22\x12\x21\x24\x42\x01\x00\xf6\xf6\xf6\xf6",
            id="move raw 3",
        ),
        pytest.param(
            ProtocolCommandRgbLed(
                ProtocolPayloadHeader(
                    0x1122334455667788, 0x1222122212221221, 0x2442, 1
                ),
                0,
                0,
                0,
            ),
            b"\x11\x22\x33\x44\x55\x66\x77\x88\x12\x22\x12\x22\x12\x22\x12\x21\x24\x42\x01\x01\x00\x00\x00",
            id="rgb led 1",
        ),
        pytest.param(
            ProtocolCommandRgbLed(
                ProtocolPayloadHeader(
                    0x1122334455667788, 0x1222122212221221, 0x2442, 1
                ),
                255,
                255,
                255,
            ),
            b"\x11\x22\x33\x44\x55\x66\x77\x88\x12\x22\x12\x22\x12\x22\x12\x21\x24\x42\x01\x01\xff\xff\xff",
            id="rgb led 2",
        ),
        pytest.param(
            ProtocolCommandRgbLed(
                ProtocolPayloadHeader(
                    0x1122334455667788, 0x1222122212221221, 0x2442, 1
                ),
                10,
                10,
                10,
            ),
            b"\x11\x22\x33\x44\x55\x66\x77\x88\x12\x22\x12\x22\x12\x22\x12\x21\x24\x42\x01\x01\n\n\n",
            id="rgb led 3",
        ),
    ],
)
def test_payload(payload, expected):
    result = payload.to_bytearray()
    assert result == expected, f"{result} != {expected}"


@pytest.mark.parametrize(
    "payload,string",
    [
        pytest.param(
            ProtocolPayloadHeader(0xFFFFFFFFFFFFFFFF, 0x0000000000000000, 0x1234, 0),
            (
                "Header: (19 bytes)\n"
                "+--------------------+--------------------+----------+---------+\n"
                "|        destination |             source | swarm id | version |\n"
                "| 0xffffffffffffffff | 0x0000000000000000 |   0x1234 |    0x00 |\n"
                "+--------------------+--------------------+----------+---------+\n"
                "\n"
            ),
            id="header",
        ),
        pytest.param(
            ProtocolCommandMoveRaw(
                ProtocolPayloadHeader(
                    0x1122334455667788, 0x1222122212221221, 0x2442, 1
                ),
                0,
                66,
                0,
                66,
            ),
            (
                "Header: (19 bytes)\n"
                "+--------------------+--------------------+----------+---------+\n"
                "|        destination |             source | swarm id | version |\n"
                "| 0x1122334455667788 | 0x1222122212221221 |   0x2442 |    0x01 |\n"
                "+--------------------+--------------------+----------+---------+\n"
                "\n"
                "Move Raw command:\n"
                "+---------+---------+---------+---------+---------+\n"
                "|    type |  left x |  left y | right x | right y |\n"
                "|       0 |       0 |      66 |       0 |      66 |\n"
                "+---------+---------+---------+---------+---------+\n"
                "\n"
            ),
            id="move raw",
        ),
        pytest.param(
            ProtocolCommandRgbLed(
                ProtocolPayloadHeader(
                    0x1122334455667788, 0x1222122212221221, 0x2442, 1
                ),
                0,
                0,
                0,
            ),
            (
                "Header: (19 bytes)\n"
                "+--------------------+--------------------+----------+---------+\n"
                "|        destination |             source | swarm id | version |\n"
                "| 0x1122334455667788 | 0x1222122212221221 |   0x2442 |    0x01 |\n"
                "+--------------------+--------------------+----------+---------+\n"
                "\n"
                "RGB LED command:\n"
                "+-------+-------+-------+-------+\n"
                "|  type |   red | green |  blue |\n"
                "|     1 |     0 |     0 |     0 |\n"
                "+-------+-------+-------+-------+\n"
                "\n"
            ),
            id="rgb led",
        ),
    ],
)
def test_payload_repr(payload, string, capsys):
    print(payload)
    out, _ = capsys.readouterr()
    assert out == string
