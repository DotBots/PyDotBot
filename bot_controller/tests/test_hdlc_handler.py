"""Test module for HDLC handler class."""

import pytest

from bot_controller.hdlc import HDLCDecodeException, HDLCState, HDLCHandler


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
    # Can't handle byte when in ready state and the received frame has not been decoded
    handler.handle_byte(b"A")
    assert handler.frame[-1].to_bytes(1, "little") == b"~"


def test_hdlc_handler_decode():
    handler = HDLCHandler()
    for byte in b"~test\x88\x07~":
        handler.handle_byte(int(byte).to_bytes(1, "little"))
    assert handler.decode() == b"test"
    assert handler.state == HDLCState.IDLE


def test_hdlc_handler_invalid_state():
    handler = HDLCHandler()
    for byte in b"~test\x42\x42":
        handler.handle_byte(int(byte).to_bytes(1, "little"))
    with pytest.raises(HDLCDecodeException) as exc:
        handler.decode()
    assert str(exc.value) == "Incomplete HDLC frame"


def test_hdlc_handler_invalid_fcs():
    handler = HDLCHandler()
    for byte in b"~test\x42\x42~":
        handler.handle_byte(int(byte).to_bytes(1, "little"))

    with pytest.raises(HDLCDecodeException) as exc:
        handler.decode()
    assert str(exc.value) == "Invalid FCS"


def test_hdlc_handler_payload_too_short():
    handler = HDLCHandler()
    for byte in b"~~":
        handler.handle_byte(int(byte).to_bytes(1, "little"))

    with pytest.raises(HDLCDecodeException) as exc:
        handler.decode()
    assert str(exc.value) == "Payload too short"
