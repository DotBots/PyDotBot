import base64
from bottle import Bottle, Route, run, request
from bot_controller import bc_serial


# Examples curl -X POST -s -d '{"cmd": "aGVsbG8K"}' -H "Content-Type: application/json" http://localhost:8080/dotbot
# curl -X POST -s -d '{"cmd": "'$(base64 <<< azazazazazazaz)'"}' -H "Content-Type: application/json"
# http://localhost:8080/dotbot


class ServerController:

    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self.active_keys = []
        self.app = Bottle()
        self.app.add_route(
            Route(self.app, "/dotbot", "POST", self.dotbot)
        )

    def dotbot(self):
        message = base64.b64decode(request.json["cmd"])
        bc_serial.write(self.port, self.baudrate, message)

    def start(self):
        run(self.app, host='0.0.0.0', port=8080)
