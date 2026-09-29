import math
from copy import deepcopy
from typing import Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from dotbot.area import Area
from dotbot.examples.charging_station.charging_station import (
    DT,
    PARK_SPACING,
    QUEUE_SPACING,
    charge_robots,
    layout_from_site,
    queue_robots,
)
from dotbot.examples.common.orca import OrcaParams
from dotbot.models import (
    DotBotLH2Position,
    DotBotModel,
    DotBotMoveRawCommandModel,
    DotBotRgbLedCommandModel,
    DotBotStatus,
    DotBotWaypoints,
    WSMessage,
)
from dotbot.protocol import ApplicationType
from dotbot.site import Site

MOVE_RAW_SCALE = 10  # displacement per raw move step

# A 2 x 2 m field with a 2 x 2 m staging area below it.
C405 = Site(
    name="c405",
    areas={
        "field": Area(0, 0, 2000, 2000, "field", "field"),
        "staging": Area(0, 2000, 2000, 2000, "staging", "staging"),
    },
)
LAYOUT = layout_from_site(C405)
QUEUE_HEAD_X, QUEUE_HEAD_Y = LAYOUT.queue_head_x, LAYOUT.queue_head_y


def test_layout_queues_on_the_border_and_charges_on_the_far_edge():
    assert (LAYOUT.queue_head_x, LAYOUT.queue_head_y) == (500, 2000)
    assert (LAYOUT.charger_x, LAYOUT.charger_y) == (500, 3900)
    assert (LAYOUT.park_x, LAYOUT.park_y) == (300, 300)
    assert LAYOUT.away == -1


def test_layout_with_staging_above_the_field():
    site = Site(
        areas={
            "staging": Area(0, 0, 4000, 1000, "staging", "staging"),
            "field": Area(0, 1000, 4000, 3000, "field", "field"),
        }
    )
    layout = layout_from_site(site)
    assert (layout.queue_head_y, layout.charger_y, layout.park_y) == (1000, 100, 3700)
    assert layout.away == 1


def test_layout_needs_a_staging_area():
    site = Site(name="bare", areas={"field": Area(0, 0, 10, 10, "field", "field")})
    with pytest.raises(ValueError, match="config init"):
        layout_from_site(site)


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

    async def fetch_dotbots(self, query=None) -> List[DotBotModel]:
        bots = list(self._dotbots.values())
        if query is not None and query.address is not None:
            bots = [b for b in bots if b.address == query.address]
        return bots

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

        # Convert bot direction to radians (matching direction_to_rad convention)
        theta = (bot.direction + 90) * math.pi / 180.0

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


class FakeDotBotWsClient:
    """
    Fake WebSocket client for testing control logic.

    - Accepts typed WSMessage objects
    - Dispatches to FakeRestClient logic
    - Records all WS messages for assertions
    """

    def __init__(self, rest_client: FakeRestClient):
        self.rest = rest_client
        self.sent_messages: list[WSMessage] = []
        self.connected = False

    async def connect(self):
        self.connected = True

    async def close(self):
        self.connected = False

    async def send(self, msg: WSMessage):
        if not self.connected:
            raise RuntimeError("FakeDotBotWsClient is not connected")

        self.sent_messages.append(msg)

        if msg.cmd == "rgb_led":
            await self.rest.send_rgb_led_command(
                address=msg.address,
                command=msg.data,
            )

        elif msg.cmd == "move_raw":
            await self.rest.send_move_raw_command(
                address=msg.address,
                application=msg.application,
                command=msg.data,
            )

        elif msg.cmd == "waypoints":
            await self.rest.send_waypoint_command(
                address=msg.address,
                application=msg.application,
                command=msg.data,
            )

        else:
            raise ValueError(f"Unknown WS command: {msg.cmd}")


def fake_bot(address: str, x: float, y: float) -> DotBotModel:
    return DotBotModel(
        address=address,
        application=ApplicationType.DotBot,
        status=DotBotStatus.ACTIVE,
        direction=0,
        lh2_position=DotBotLH2Position(x=x, y=y),
        last_seen=0,
    )


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_queue_robots_converges_to_queue_positions(_):
    bots = [
        fake_bot("B", x=500, y=0),
        fake_bot("A", x=100, y=0),
        fake_bot("C", x=900, y=0),
    ]

    client = FakeRestClient(bots)
    ws = FakeDotBotWsClient(client)
    await ws.connect()
    params = OrcaParams(time_horizon=5 * DT, time_step=DT)

    await queue_robots(client, ws, bots, params, LAYOUT)

    # Bots should be ordered A, B, C along the queue
    expected = {
        "B": QUEUE_HEAD_X + 0 * QUEUE_SPACING,
        "A": QUEUE_HEAD_X + 1 * QUEUE_SPACING,
        "C": QUEUE_HEAD_X + 2 * QUEUE_SPACING,
    }

    for address, expected_x in expected.items():
        bot = client._dotbots[address]

        # X, Y coordinate matches queue spacing
        assert math.isclose(bot.lh2_position.x, expected_x, abs_tol=100)
        assert math.isclose(bot.lh2_position.y, QUEUE_HEAD_Y, abs_tol=100)

    # Waypoints were actually sent
    assert len(client.waypoint_commands)


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
    ws = FakeDotBotWsClient(client)
    await ws.connect()
    params = OrcaParams(time_horizon=5 * DT, time_step=DT)

    await charge_robots(client, ws, params, LAYOUT)

    # --- Assertions: all bots parked ---
    # Bots should be ordered A, B, C along the park slots
    expected = {
        "A": LAYOUT.park_x + 0 * PARK_SPACING,
        "B": LAYOUT.park_x + 1 * PARK_SPACING,
        "C": LAYOUT.park_x + 2 * PARK_SPACING,
    }

    for address, expected_x in expected.items():
        bot = client._dotbots[address]

        assert math.isclose(bot.lh2_position.x, expected_x, abs_tol=100)
        assert math.isclose(bot.lh2_position.y, LAYOUT.park_y, abs_tol=100)

    # LEDs were used during charging
    assert len(client.rgb_commands) >= 2 * len(bots)

    # Raw moves were issued to disengage bots
    assert len(client.move_raw_commands) > 0

    # Waypoints were issued for charging + parking
    assert len(client.waypoint_commands) > 0
