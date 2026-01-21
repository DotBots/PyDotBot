from dotbot.models import WSMessage


class DotBotWsClient:
    def __init__(self, host, port):
        self.url = f"ws://{host}:{port}/controller/ws/dotbots"
        self.ws = None

    async def connect(self):
        import websockets

        self.ws = await websockets.connect(self.url)

    async def close(self):
        await self.ws.close()

    async def send(self, msg: WSMessage):
        if not self.ws:
            raise RuntimeError("WebSocket not connected")
        await self.ws.send(msg.model_dump_json())
