from unittest import mock

import httpx
import pytest

from dotbot.models import DotBotMoveRawCommandModel, DotBotRgbLedCommandModel
from dotbot.protocol import ApplicationType
from dotbot.rest import RestClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,expected",
    [
        pytest.param(httpx.Response(200, json=[]), [], id="empty"),
        pytest.param(httpx.ConnectError, [], id="http error"),
        pytest.param(httpx.Response(403), [], id="http code error"),
        pytest.param(
            httpx.Response(200, json=[{"address": "test", "status": 1}]),
            [],
            id="none active",
        ),
        pytest.param(
            httpx.Response(200, json=[{"address": "test", "status": 0}]),
            [{"address": "test", "status": 0}],
            id="found",
        ),
    ],
)
@mock.patch("httpx.AsyncClient.get")
async def test_fetch_active_dotbots(get, response, expected):
    if response == httpx.ConnectError:
        get.side_effect = response("error")
    else:
        get.return_value = response
    client = RestClient("localhost", 1234, False)
    result = await client.fetch_active_dotbots()
    get.assert_called_once()
    assert result == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,application,command",
    [
        pytest.param(
            httpx.Response(200),
            ApplicationType.DotBot,
            DotBotMoveRawCommandModel(left_x=0, left_y=0, right_x=0, right_y=0),
            id="dotbot",
        ),
        pytest.param(
            httpx.Response(200),
            ApplicationType.SailBot,
            DotBotMoveRawCommandModel(left_x=0, left_y=0, right_x=0, right_y=0),
            id="sailbot",
        ),
        pytest.param(
            httpx.ConnectError,
            ApplicationType.DotBot,
            DotBotMoveRawCommandModel(left_x=0, left_y=0, right_x=0, right_y=0),
            id="http error",
        ),
        pytest.param(
            httpx.Response(403),
            ApplicationType.DotBot,
            DotBotMoveRawCommandModel(left_x=0, left_y=0, right_x=0, right_y=0),
            id="invalid http code",
        ),
    ],
)
@mock.patch("httpx.AsyncClient.put")
async def test_send_move_raw_command(put, response, application, command):
    if response == httpx.ConnectError:
        put.side_effect = response("error")
    else:
        put.return_value = response
    client = RestClient("localhost", 1234, False)
    await client.send_move_raw_command("test", application, command)
    put.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,command",
    [
        pytest.param(
            httpx.Response(200),
            DotBotRgbLedCommandModel(red=0, green=0, blue=0),
            id="ok",
        ),
        pytest.param(
            httpx.ConnectError,
            DotBotRgbLedCommandModel(red=0, green=0, blue=0),
            id="http error",
        ),
        pytest.param(
            httpx.Response(403),
            DotBotRgbLedCommandModel(red=0, green=0, blue=0),
            id="invalid http code",
        ),
    ],
)
@mock.patch("httpx.AsyncClient.put")
async def test_send_rgb_led_command(put, response, command):
    if response == httpx.ConnectError:
        put.side_effect = response("error")
    else:
        put.return_value = response
    client = RestClient("localhost", 1234, False)
    await client.send_rgb_led_command("test", command)
    put.assert_called_once()
