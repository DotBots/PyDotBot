"""Tests for the simulated DotBot's receive path."""

import queue

import pytest
from dotbot_utils.protocol import Frame, Header, Packet

from dotbot import addr_to_hex
from dotbot.dotbot_simulator import DotBotSimulator, SimulatedDotBotSettings
from dotbot.protocol import PayloadCommandMoveRaw


def _bot(address: str) -> DotBotSimulator:
    return DotBotSimulator(
        SimulatedDotBotSettings(address=address, pos_x=100, pos_y=100),
        queue.Queue(),
    )


def _move_raw(destination: int) -> Frame:
    return Frame(
        header=Header(destination=destination, source=0),
        packet=Packet().from_payload(
            PayloadCommandMoveRaw(left_x=0, left_y=80, right_x=0, right_y=80)
        ),
    )


def _deliver(bot: DotBotSimulator, frame: Frame) -> None:
    """Run one pass of the rx loop over a single frame."""
    bot.queue.put(frame)
    bot.queue.put(None)  # breaks the loop once the frame is handled
    bot.rx_frame()


@pytest.mark.parametrize(
    "address",
    [
        "B0B0F00D33333333",  # letters: fails if the two sides disagree on case
        "00B0F00D33333333",  # leading zero: fails if the address is not padded
        "1234567890123456",  # digits only: matches under either convention
    ],
)
def test_a_command_addressed_to_this_bot_is_applied(address):
    bot = _bot(address)
    _deliver(bot, _move_raw(int(address, 16)))
    assert bot.pwm_left == 80
    assert bot.pwm_right == 80


def test_a_command_for_another_bot_is_ignored():
    bot = _bot("B0B0F00D33333333")
    _deliver(bot, _move_raw(0xDEADBEEF22222222))
    assert bot.pwm_left == 0
    assert bot.pwm_right == 0


def test_the_address_rendering_round_trips():
    """The rx path and the index map must render an address the same way."""
    for address in ("B0B0F00D33333333", "00B0F00D33333333", "1234567890123456"):
        assert addr_to_hex(int(address, 16)) == address
