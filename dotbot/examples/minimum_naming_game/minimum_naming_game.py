import asyncio
import os
from typing import List

from dotbot.models import (
    DotBotLH2Position,
    DotBotModel,
    DotBotQueryModel,
    DotBotRgbLedCommandModel,
    DotBotStatus,
    DotBotWaypoints,
    WSRgbLed,
)
from dotbot.protocol import ApplicationType
from dotbot.rest import RestClient, rest_client
from dotbot.websocket import DotBotWsClient

from dotbot.examples.minimum_naming_game.controller import Controller

import numpy as np
import random
from scipy.spatial import cKDTree

COMM_RANGE=250
THRESHOLD=50

# TODO: Measure these values for real dotbots
BOT_RADIUS = 40  # Physical radius of a DotBot (unit), used for collision avoidance

dotbot_controllers = dict()


async def fetch_active_dotbots(client: RestClient) -> List[DotBotModel]:
    return await client.fetch_dotbots(
        query=DotBotQueryModel(status=DotBotStatus.ACTIVE)
    )


async def main() -> None:
    url = os.getenv("DOTBOT_CONTROLLER_URL", "localhost")
    port = os.getenv("DOTBOT_CONTROLLER_PORT", "8000")
    use_https = os.getenv("DOTBOT_CONTROLLER_USE_HTTPS", False)
    sct_path = os.getenv("DOTBOT_SCT_PATH", "dotbot/examples/minimum_naming_game/models/supervisor.yaml")

    async with rest_client(url, port, use_https) as client:
        dotbots = await fetch_active_dotbots(client)

        # print(len(dotbots), "dotbots connected.")

        # Initialization
        for dotbot in dotbots:

            # Init controller
            controller = Controller(dotbot.address, sct_path)
            dotbot_controllers[dotbot.address] = controller    
            # print(f'type of controller: {type(controller)} for DotBot {dotbot.address}')   

        # 1. Extract positions into a list of [x, y] coordinates
        coords = [[dotbot.lh2_position.x, dotbot.lh2_position.y] for dotbot in dotbots]

        # 2. Convert the list to a NumPy array
        positions = np.array(coords)

        # 3. Build the KD-Tree
        # This tree can now be used for fast spatial queries (like finding neighbors)
        tree = cKDTree(positions)

        ws = DotBotWsClient(url, port)
        await ws.connect()
        try:

            counter = 0

            while True:
                print("Step", counter)

                for dotbot in dotbots:

                    controller = dotbot_controllers[dotbot.address]
                    controller.position = dotbot.lh2_position
                    controller.direction = dotbot.direction

                    # print(f'Controller position: {controller.position}, direction: {controller.direction}')

                    # 1. Query the tree for indices of neighbors
                    neighbor_indices = tree.query_ball_point([dotbot.lh2_position.x, dotbot.lh2_position.y], r=COMM_RANGE)
                    
                    # 2. Convert indices back into actual DotBot objects
                    neighbors = [
                        dotbots[idx] for idx in neighbor_indices 
                        if dotbots[idx].address != dotbot.address
                    ]

                    # print(f'neighbour of {dotbot.address}: {[n.address for n in neighbors]}')

                    # 3. If there are neighbors broadcasting, pick ONE randomly to listen to
                    if neighbors:
                        selected_neighbor = dotbot_controllers[random.choice(neighbors).address]

                        # Share the word: take the neighbor's chosen word index
                        if selected_neighbor.w_index != 0:
                            controller.received_word = selected_neighbor.w_index
                        
                            # Set the flags so the robot knows it has a new message to process
                            controller.new_word_received = True
                            controller.received_word_checked = False
                        
                    # Update controller's neighbor list
                    controller.neighbors = neighbors
                        
                    # Run controller
                    controller.control_step() # run SCT step

                    # Force update
                    waypoints = DotBotWaypoints(
                            threshold=THRESHOLD,
                            waypoints=[
                                DotBotLH2Position(
                                    x=dotbots[0].lh2_position.x, y=dotbots[0].lh2_position.y, z=0
                                )
                            ],
                        )
                    await client.send_waypoint_command(
                        address=dotbots[0].address,
                        application=ApplicationType.DotBot,
                        command=waypoints,
                    )

                    await ws.send(
                        WSRgbLed(
                            cmd="rgb_led",
                            address=dotbot.address,
                            application=ApplicationType.DotBot,
                            data=DotBotRgbLedCommandModel(
                                red=controller.led[0],
                                green=controller.led[1],
                                blue=controller.led[2],
                            ),
                        )
                    )

                # await asyncio.sleep(0.1)
                counter += 1
        finally:
            await ws.close()

    return None


if __name__ == "__main__":
    asyncio.run(main())
