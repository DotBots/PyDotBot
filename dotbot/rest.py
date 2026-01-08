# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module containing client code to interact with the controller REST API."""

from contextlib import asynccontextmanager
from typing import List

import httpx

from dotbot.logger import LOGGER, setup_logging
from dotbot.models import DotBotModel, DotBotStatus
from dotbot.protocol import ApplicationType


@asynccontextmanager
async def rest_client(host, port, https):
    client = RestClient(host, port, https)
    try:
        yield client
    finally:
        await client.close()


class RestClient:
    """Client to interact with the controller REST API."""

    def __init__(self, hostname, port, https):
        self.hostname = hostname
        self.port = port
        self.https = https
        setup_logging(None, "info", ["console"])
        self._logger = LOGGER.bind(context=__name__)
        self._client = httpx.AsyncClient()

    @property
    def base_url(self):
        """Returns the base URL of the controller REST API."""
        return f"{'https' if self.https else 'http'}://{self.hostname}:{self.port}/controller"

    async def close(self):
        await self._client.aclose()

    async def fetch_active_dotbots(self) -> List[DotBotModel]:
        """Fetch active DotBots."""
        try:
            response = await self._client.get(
                f"{self.base_url}/dotbots",
                headers={
                    "Accept": "application/json",
                },
            )
        except httpx.ConnectError as exc:
            self._logger.warning(f"Failed to fetch dotbots: {exc}")
        else:
            if response.status_code != 200:
                self._logger.warning(
                    f"Failed to fetch dotbots: {response} {response.text}"
                )
            else:
                return [
                    DotBotModel(**dotbot)
                    for dotbot in response.json()
                    if dotbot["status"] == DotBotStatus.ACTIVE.value
                ]
        return []

    async def _send_command(self, address, application, resource, command):
        try:
            response = await self._client.put(
                f"{self.base_url}/dotbots" f"/{address}/{application.value}/{resource}",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                content=command.model_dump_json(),
            )
        except httpx.ConnectError as exc:
            self._logger.warning(f"Failed to send command: {exc}")
            return
        if response.status_code != 200:
            self._logger.error(
                "Cannot send command",
                response=str(response),
                status_code=response.status_code,
                content=str(response.text),
            )

    async def send_move_raw_command(self, address, application, command):
        """Send a move raw command to a DotBot."""
        await self._send_command(address, application, "move_raw", command)

    async def send_rgb_led_command(self, address, command):
        """Send an RGB LED command to a DotBot."""
        await self._send_command(address, ApplicationType.SailBot, "rgb_led", command)

    async def send_waypoint_command(self, address, application, command):
        """Send an waypoint command to a DotBot."""
        await self._send_command(address, application, "waypoints", command)
