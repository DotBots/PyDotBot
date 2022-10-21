from unittest.mock import MagicMock

import pytest

from fastapi.testclient import TestClient

from bot_controller.models import DotBotAddressModel
from bot_controller.server import app


client = TestClient(app)


@pytest.mark.asyncio
async def test_openapi_exists():
    response = client.get("/api")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_controller_dotbot_address():
    app.controller = MagicMock()
    app.controller.header = MagicMock()
    app.controller.header.destination = MagicMock()
    result_address = "0000000000004242"
    result = DotBotAddressModel(address=result_address)
    app.controller.header.destination = int(result_address, 16)
    response = client.get("/controller/dotbot_address")
    assert response.status_code == 200
    assert response.json() == result.dict()
