import asyncio
import os

from dotbot.models import DotBotQueryModel, DotBotStatus, DotBotWaypoints, WSWaypoints
from dotbot.rest import rest_client
from dotbot.websocket import DotBotWsClient

"""
This example shows how to stop a dotbot swarm. Run it with:
python -m dotbot.examples.stop
"""


async def main() -> None:
    url = os.getenv("DOTBOT_CONTROLLER_URL", "localhost")
    port = os.getenv("DOTBOT_CONTROLLER_PORT", "8000")
    use_https = os.getenv("DOTBOT_CONTROLLER_USE_HTTPS", False)

    async with rest_client(url, port, use_https) as client:
        dotbots = await client.fetch_dotbots(
            query=DotBotQueryModel(status=DotBotStatus.ACTIVE)
        )

        ws = DotBotWsClient(url, port)
        await ws.connect()
        try:
            for dotbot in dotbots:
                await ws.send(
                    WSWaypoints(
                        cmd="waypoints",
                        address=dotbot.address,
                        application=dotbot.application,
                        data=DotBotWaypoints(
                            threshold=0,
                            waypoints=[],
                        ),
                    )
                )
        finally:
            await ws.close()


if __name__ == "__main__":
    asyncio.run(main())
