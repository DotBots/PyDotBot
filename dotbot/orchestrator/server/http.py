"""
COMMON HTTP STATUS CODES:
200 - OK
201 - Created
400 - Bad Request
401 - Unauthorized
403 - Forbidden
404 - Not Found
405 - Method Not Allowed
409 - Conflict
418 - I'm a teapot ;) (RFC 2324 Hyper Text Coffee Pot Control Protocol)
500 - Internal Server Error
501 - Not Implemented
502 - Bad Gateway
503 - Service Unavailable
"""

from flask import Flask, request, jsonify
from flask_classful import FlaskView, route

from dotbot.orchestrator.gateway import Gateway
from dotbot.orchestrator import OrchestratorConfig, DefaultConfig

app = Flask(__name__)

class DebugType:
    No = 0
    Dry = 1
    Verbose = 2

class OrchestratorHTTP:
    def __init__(self, config: OrchestratorConfig = DefaultConfig(), debug: DebugType = DebugType.No):
        self.config = config
        self.debug = debug

        global parent
        parent = self

        OrchestratorFlask.register(app, route_base="/")

    def run(self):
        http_conf = self.config.orch.http
        app.run(http_conf.host, http_conf.port, debug=False)

parent = None # NOTE: There should only ever be one server running on a device yes? Or might there be multiple gateways connected

class OrchestratorFlask(FlaskView):
    orch_config = DefaultConfig()
    debug_type = DebugType.Dry

    def __init__(self):
        super().__init__()
        self.orch_config = parent.config
        self.debug_type = parent.debug

    def index(self):
        """landing page"""
        return "Welcome to the DotBot HTTP Orchestrator Landing Page!" # render_template('index.html')

    @route("/api/v1/orch/<id>/status", methods=["GET"])
    def orch_status(self, id):
        print(self)
        response = {"gateway_id": id, "firmware_version": "v1", "number_dotbots": 1}
        return jsonify(response), 200

    @route("/api/v1/dotbot/list", methods=["GET"])
    def dotbot_list(self):
        print(self)
        response = {"number_dotbots": 1, "dotbots": [{"dotbot_id": 0, "gateway_id": 0, "timestamp": 0}]}
        return jsonify(response), 200

    @app.route("/api/v1/dotbot/<id>/status", methods=["GET"])
    def dotbot_status(self, id):
        print(self)
        return 501  # TODO: implement

    @route("/api/v1/dotbot/<id>/command/move", methods=["POST"])
    def dotbot_move(self, id):
        print(self)
        request_dict = request.get_json()
        print("Move request received -- Args: {}, JSON: {}".format(request.args, request_dict))

        serial_conf = self.orch_config.orch.client.gateway.serial

        lin_vel = request_dict.get('linear_vel', "")
        ang_vel = request_dict.get('angular_vel', "")

        if self.debug_type in [DebugType.Dry]:
            return "Dry run", 201

        gateway = Gateway(port=serial_conf.port, baud=serial_conf.baud)

        success = gateway.command_move(float(lin_vel), float(ang_vel))  # TODO: should handle dotbot id
        gateway.close()

        return ("Success!", 200) if success else ("Failed", 500)

    @route("/api/v1/dotbot/<id>/command/led", methods=["POST"])
    def dotbot_led(self, id):
        print(self)
        request_dict = request.get_json()
        print("LED request received -- Args: {}, JSON: {}".format(request.args, request_dict))

        return "Not yet implemented", 501  # TODO: implement - led firmware

    @route("/api/v1/gateway/<id>/reload", methods=["GET"])
    def gateway_reload(self, id):
        print(self)
        gateway_conf = self.orch_config.orch.client.gateway

        print(f"Copying from {gateway_conf.bin} to {gateway_conf.mount}...")

        if self.debug_type in [DebugType.Dry]:
            return "Dry run", 201

        Gateway.load_binary(gateway_conf.bin, gateway_conf.mount)

        return f"Copied from {gateway_conf.bin} to {gateway_conf.mount}", 200

    # TODO: notification routes