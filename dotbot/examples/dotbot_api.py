from typing import List

import httpx

from dotbot.models import (
    DotBotModel,
    DotBotQueryModel,
    DotBotWaypoints,
)


async def get_dotbots(
    client: httpx.AsyncClient, query: DotBotQueryModel
) -> List[DotBotModel]:
    resp = await client.get(
        "/controller/dotbots",
        params={
            "application": query.application.value,
            "status": query.status.value,
        },
    )
    resp.raise_for_status()

    return [DotBotModel(**d) for d in resp.json()]


async def set_dotbot_rgb_led(
    client: httpx.AsyncClient,
    *,
    address: str,
    application: int,
    red: int,
    green: int,
    blue: int,
) -> None:
    resp = await client.put(
        f"/controller/dotbots/{address}/{application}/rgb_led",
        json={
            "red": red,
            "green": green,
            "blue": blue,
        },
    )
    resp.raise_for_status()


async def move_dotbot_raw(
    client: httpx.AsyncClient,
    *,
    address: str,
    application: int,
    left_x: int,
    right_x: int,
    left_y: int,
    right_y: int,
) -> None:
    resp = await client.put(
        f"/controller/dotbots/{address}/{application}/move_raw",
        json={
            "left_x": left_x,
            "right_x": right_x,
            "left_y": left_y,
            "right_y": right_y,
        },
    )
    resp.raise_for_status()


async def set_dotbot_waypoints(
    client: httpx.AsyncClient,
    *,
    address: str,
    application: int,
    waypoints: DotBotWaypoints,
) -> None:
    resp = await client.put(
        f"/controller/dotbots/{address}/{application}/waypoints",
        json=waypoints.model_dump(),
    )
    resp.raise_for_status()
