import base64
from bottle import Bottle, Route, run, request
from bot_controller.controller import ControllerBase


# Examples curl -X POST -s -d '{"cmd": "aGVsbG8K"}' -H "Content-Type: application/json" http://localhost:8080/dotbot
# curl -X POST -s -d '{"cmd": "'$(base64 <<< azazazazazazaz)'"}' -H "Content-Type: application/json"
# http://localhost:8080/dotbot


class ServerController(ControllerBase):

    def init(self):
        self.active_keys = []
        self.app = Bottle()
        self.app.add_route(
            Route(self.app, "/dotbot", "POST", self.dotbot)
        )

    def dotbot(self):
        self.write(base64.b64decode(request.json["cmd"]))

    def start(self):
        run(self.app, host='0.0.0.0', port=8080)
