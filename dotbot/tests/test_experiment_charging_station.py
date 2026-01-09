import math
from copy import deepcopy
from typing import Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from dotbot.examples.charging_station import (
    DT,
    PARK_SPACING,
    PARK_X,
    PARK_Y,
    QUEUE_HEAD_X,
    QUEUE_HEAD_Y,
    QUEUE_SPACING,
    charge_robots,
    queue_robots,
)
from dotbot.examples.orca import OrcaParams
from dotbot.models import (
    DotBotLH2Position,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
    DotBotStatus,
    DotBotWaypoints,
)
from dotbot.protocol import ApplicationType

MOVE_RAW_SCALE = 0.001  # small, deterministic displacement


class FakeRestClient:
    """
    Fake RestClient for testing control logic.

    - Stores DotBots in memory
    - Teleports bots to waypoints immediately
    - Records all commands for assertions
    """

    def __init__(self, dotbots: List[DotBotModel]):
        # Store bots by address (copy to avoid mutating test fixtures)
        self._dotbots: Dict[str, DotBotModel] = {
            b.address: deepcopy(b) for b in dotbots
        }

        # Command logs (for assertions)
        self.waypoint_commands = []
        self.move_raw_commands = []
        self.rgb_commands = []

    async def fetch_active_dotbots(self) -> List[DotBotModel]:
        return list(self._dotbots.values())

    async def send_waypoint_command(
        self,
        *,
        address: str,
        application: ApplicationType,
        command: DotBotWaypoints,
    ):
        self.waypoint_commands.append((address, command))

        bot = self._dotbots[address]
        wp = command.waypoints[0]

        # Compute displacement
        dx = wp.x - bot.lh2_position.x
        dy = wp.y - bot.lh2_position.y

        # Update direction if there is movement
        if dx != 0 or dy != 0:
            # atan2 gives angle from +X axis
            angle_rad = math.atan2(dy, dx)

            # Convert back to DotBot direction convention
            # Inverse of: rad = (direction + 90) * pi / 180
            direction_deg = math.degrees(angle_rad) - 90

            # Normalize to [-180, 180]
            direction_deg = math.atan2(
                math.sin(math.radians(direction_deg)),
                math.cos(math.radians(direction_deg)),
            )
            direction_deg = math.degrees(direction_deg)

            bot.direction = direction_deg

        # TELEPORT bot to waypoint (instant convergence)
        bot.lh2_position = DotBotLH2Position(
            x=wp.x,
            y=wp.y,
            z=wp.z,
        )

    async def send_move_raw_command(
        self,
        *,
        address: str,
        application: ApplicationType,
        command: DotBotMoveRawCommandModel,
    ):
        self.move_raw_commands.append((address, command))

        bot = self._dotbots[address]

        # Average forward/backward command
        forward = (command.left_y + command.right_y) / 2.0

        if forward == 0:
            return

        # Convert bot direction (degrees) to radians
        theta = math.radians(bot.direction)

        # Move along heading
        dx = math.cos(theta) * forward * MOVE_RAW_SCALE
        dy = math.sin(theta) * forward * MOVE_RAW_SCALE

        bot.lh2_position.x += dx
        bot.lh2_position.y += dy

    async def send_rgb_led_command(
        self,
        *,
        address: str,
        command: DotBotRgbLedCommandModel,
    ):
        self.rgb_commands.append((address, command))


def fake_bot(address: str, x: float, y: float) -> DotBotModel:
    return DotBotModel(
        address=address,
        application=ApplicationType.DotBot,
        status=DotBotStatus.ACTIVE,
        direction=0,
        lh2_position=DotBotLH2Position(x=x, y=y, z=0),
        last_seen=0,
    )


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_queue_robots_converges_to_queue_positions(_):
    bots = [
        fake_bot("B", x=0.5, y=0.0),
        fake_bot("A", x=0.1, y=0.0),
        fake_bot("C", x=0.9, y=0.0),
    ]

    client = FakeRestClient(bots)
    params = OrcaParams(time_horizon=DT)

    await queue_robots(client, bots, params)

    # Bots should be ordered A, B, C along the queue
    expected = {
        "A": QUEUE_HEAD_X + 0 * QUEUE_SPACING,
        "B": QUEUE_HEAD_X + 1 * QUEUE_SPACING,
        "C": QUEUE_HEAD_X + 2 * QUEUE_SPACING,
    }

    for address, expected_x in expected.items():
        bot = client._dotbots[address]

        # X, Y coordinate matches queue spacing
        assert math.isclose(bot.lh2_position.x, expected_x, abs_tol=0.05)
        assert math.isclose(bot.lh2_position.y, QUEUE_HEAD_Y, abs_tol=0.05)

    # Waypoints were actually sent
    assert len(client.waypoint_commands) == 39


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_charge_robots_moves_all_bots_to_parking(_):
    # Start bots already queued
    bots = [
        fake_bot("A", x=QUEUE_HEAD_X + 1 * QUEUE_SPACING, y=QUEUE_HEAD_Y),
        fake_bot("B", x=QUEUE_HEAD_X + 2 * QUEUE_SPACING, y=QUEUE_HEAD_Y),
        fake_bot("C", x=QUEUE_HEAD_X + 3 * QUEUE_SPACING, y=QUEUE_HEAD_Y),
    ]

    client = FakeRestClient(bots)
    params = OrcaParams(time_horizon=DT)

    await charge_robots(client, params)

    # --- Assertions: all bots parked ---
    # Bots should be ordered A, B, C along the park slots
    expected = {
        "A": PARK_Y + 0 * PARK_SPACING,
        "B": PARK_Y + 1 * PARK_SPACING,
        "C": PARK_Y + 2 * PARK_SPACING,
    }

    for address, expected_y in expected.items():
        bot = client._dotbots[address]

        # X, Y coordinate matches queue spacing
        assert math.isclose(bot.lh2_position.x, PARK_X, abs_tol=0.05)
        assert math.isclose(bot.lh2_position.y, expected_y, abs_tol=0.05)

    # LEDs were used during charging
    assert len(client.rgb_commands) >= 2 * len(bots)

    # Raw moves were issued to disengage bots
    assert len(client.move_raw_commands) > 0

    # Waypoints were issued for charging + parking
    assert len(client.waypoint_commands) > 0
