import base64
import os
from bottle import run, post, request
import bc_serial


# Examples curl -X POST -s -d '{"cmd": "aGVsbG8K"}' -H "Content-Type: application/json" http://localhost:8080/dotbot
# curl -X POST -s -d '{"cmd": "'$(base64 <<< azazazazazazaz)'"}' -H "Content-Type: application/json"
# http://localhost:8080/dotbot


GW_TTY_PORT = os.getenv("GW_TTY_PORT", "/dev/ttyACM0")
GW_TTY_BAUDRATE = int(os.getenv("GW_TTY_BAUDRATE", 115200))


@post('/dotbot')
def dotbot():
    message = base64.b64decode(request.json["cmd"])
    bc_serial.write(GW_TTY_PORT, GW_TTY_BAUDRATE, message)


def start():
    run(host='0.0.0.0', port=8080)


if __name__ == "__main__":
    start()
