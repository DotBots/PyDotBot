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

import flask
from flask import Flask, send_file, Response, request, jsonify
import os, json, zipfile, sys, requests, base64, pickle, traceback
import numpy as np
from os.path import exists
from time import time
from subprocess import Popen

app = Flask(__name__)

@app.route("/")
def home():
    """landing page"""
    return "Welcome to the DotBot Orchestrator Landing Page!"

@app.route("/api/v1/orch/<id>/status", methods=["GET"])
def orch_status(id):
    response = {"gateway_id": id, "firmware_version": "v1", "number_dotbots": 1}
    return jsonify(response), 200

@app.route("/api/v1/dotbot/list", methods=["GET"])
def dotbot_list():
    response = {"number_dotbots": 1, "dotbots": [{"dotbot_id" : 0, "gateway_id": 0, "timestamp": 0}]}
    return jsonify(response), 200

@app.route("/api/v1/dotbot/<id>/status", methods=["GET"])
def dotbot_status(id):
    return 501 # TODO: implement

@app.route("/api/v1/dotbot/<id>/command/move", methods=["POST"])
def dotbot_move(id):
    request_dict = request.get_json()
    print("Move request received -- Args: {}, JSON: {}".format(request.args, request_dict))

    lin_vel = request_dict.get('linear_vel', "")
    ang_vel = request_dict.get('angular_vel', "")

    return "Not yet implemented", 501 # TODO: implement

@app.route("/api/v1/dotbot/<ID>/command/led", methods=["POST"])
def dotbot_led(id):
    request_dict = request.get_json()
    print("LED request received -- Args: {}, JSON: {}".format(request.args, request_dict))

    return "Not yet implemented", 501 # TODO: implement - led firmware

# TODO: notification routes