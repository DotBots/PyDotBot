"""Test module for HDLC handler class."""

import pytest

from dotbot.hdlc import HDLCDecodeException, HDLCHandler, HDLCState


def test_hdlc_handler_states():
    handler = HDLCHandler()
    assert handler.state == HDLCState.IDLE
    handler.handle_byte(b"A")
    assert handler.state == HDLCState.IDLE
    handler.handle_byte(b"~")
    assert handler.state == HDLCState.RECEIVING
    handler.handle_byte(b"A")
    assert handler.state == HDLCState.RECEIVING
    handler.handle_byte(b"~")
    assert handler.state == HDLCState.READY
    handler.handle_byte(b"~")
    assert handler.state == HDLCState.RECEIVING
    handler.handle_byte(b"A")
    handler.handle_byte(b"\xf5")
    handler.handle_byte(b"\xa3")
    assert handler.state == HDLCState.RECEIVING
    handler.handle_byte(b"~")
    assert handler.state == HDLCState.READY
    handler.handle_byte(b"~")
    assert handler.state == HDLCState.RECEIVING
    handler.handle_byte(b"~")
    assert handler.output == bytearray()
    assert handler.state == HDLCState.RECEIVING
    handler.handle_byte(b"~")
    assert handler.output == bytearray()
    assert handler.state == HDLCState.RECEIVING


def test_hdlc_handler_decode():
    handler = HDLCHandler()
    for byte in b"~test\x88\x07~":
        handler.handle_byte(int(byte).to_bytes(1, "little"))
    assert handler.payload == b"test"
    assert handler.state == HDLCState.IDLE


def test_hdlc_handler_decode_with_flags():
    handler = HDLCHandler()
    for byte in b"~}^test}]\x06\x94~":
        handler.handle_byte(int(byte).to_bytes(1, "little"))
    assert handler.state == HDLCState.READY
    assert handler.payload == bytearray(b"~test}")
    assert handler.state == HDLCState.IDLE


def test_hdlc_handler_invalid_state():
    handler = HDLCHandler()
    for byte in b"~test\x42\x42":
        handler.handle_byte(int(byte).to_bytes(1, "little"))
    with pytest.raises(HDLCDecodeException) as exc:
        _ = handler.payload
    assert str(exc.value) == "Incomplete HDLC frame"


def test_hdlc_handler_invalid_fcs():
    handler = HDLCHandler()
    for byte in b"~test\x42\x42~":
        handler.handle_byte(int(byte).to_bytes(1, "little"))
    payload = handler.payload
    assert payload == bytearray()


def test_hdlc_handler_payload_too_short():
    handler = HDLCHandler()
    for byte in b"~a~":
        handler.handle_byte(int(byte).to_bytes(1, "little"))
    payload = handler.payload
    assert payload == bytearray()
