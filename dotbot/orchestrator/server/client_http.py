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

from flask import Flask, request, jsonify, render_template
from flask_classful import FlaskView, route
from flask_cors import CORS

from dotbot.orchestrator.gateway import Gateway
from dotbot.orchestrator import OrchestratorConfig

from threading import Thread
import time

app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})

class OrchestratorHTTP:
    '''
    Orchestrator http server
    '''
    def __init__(self):
        _OrchestratorFlask.register(app, route_base="/")
        
        # Initialize Gateway serial process(es)
        self.config = OrchestratorConfig().orch
        self.gateway = Gateway(**self.config.client.gateway) 
        self.status_thread = Thread(target=self.gateway.continuous_status_read, daemon=True) # this thread keeps reading the serial port continuously

    def run(self):
        '''
        Start the http server
        '''
        self.status_thread.start()
        http_conf = self.config.http
        app.run(http_conf.host, http_conf.port, debug=False, threaded=True) # NOTE: make sure only 1 process

class _OrchestratorFlask(FlaskView):
    config = OrchestratorConfig().orch # load configuration from file
    last_sent = 0

    def __init__(self):
        super().__init__()

    def index(self):
        """landing page"""
        return render_template('index.html')

    @route("/api/v1/orch/<id>/status", methods=["GET"])
    def orch_status(self, id):
        response = {"gateway_id": id, "firmware_version": "v1", "number_dotbots": 1}
        return jsonify(response), 200

    @route("/api/v1/dotbot/list", methods=["GET"])
    def dotbot_list(self):
        # response = {"number_dotbots": 1, "dotbots": [{"dotbot_id": 0, "gateway_id": 0, "timestamp": 0}]}
        dotbots = Gateway().get_dotbots()
        response = {"number_dotbots": len(dotbots), "dotbots": dotbots}
        return jsonify(response), 200

    @app.route("/api/v1/dotbot/<id>/status", methods=["GET"])
    def dotbot_status(self, id):
        return 501  # TODO: implement

    @route("/api/v1/dotbot/<id>/command/move", methods=["POST"])
    def dotbot_move(self, id):
        request_dict = request.get_json() or request.form
        print("Move request received -- Args: {}, JSON: {}, Body {}".format(request.args, request.get_json(), request.form))

        control_rate = float(self.config.control.rate_hz)

        lin_vel = request_dict.get("lin_vel", "")
        ang_vel = request_dict.get("ang_vel", "")
        # TODO: also get desired dotbot ID

        if self.config.debug or time.time() - self.last_sent < 1.0 / control_rate:
            return "Dry run", 201

        self.last_sent = time.time()

        success = Gateway().command_move(linear=float(lin_vel), angular=float(ang_vel), id=id)  # TODO: should handle dotbot id

        return ("Success!", 200) if success else ("Failed", 500)

    @route("/api/v1/dotbot/<id>/command/led", methods=["POST"])
    def dotbot_led(self, id):
        request_dict = request.get_json()
        print("LED request received -- Args: {}, JSON: {}".format(request.args, request_dict))
        
        request_dict = request.get_json() or request.form
        color = request_dict.get("color", "")

        r = min(255, color["r"])
        g = min(255, color["g"])
        b = min(255, color["b"])

        success = Gateway().command_led(color=(r, g, b), id=id)  # TODO: should handle dotbot id
        return ("Success!", 200) if success else ("Failed", 500)

    @route("/demo", methods=["GET"])
    def joy_demo(self):
        default_dotbot = request.args.get('dotbot', default=None, type=str)
        if default_dotbot is None or default_dotbot not in self.config.demo.dotbots:
            return render_template("joy.html", DEFAULT_DOTBOT=None, DOTBOT_COLOR=None)
        
        else:
            idx = self.config.demo.dotbots.index(default_dotbot)
            color = "blue" if idx % 2 == 0 else "red"
            return render_template("joy.html", DEFAULT_DOTBOT=default_dotbot, DOTBOT_COLOR=color)

    # TODO: notification routes

if __name__ == "__main__":
    OrchestratorHTTP().run()