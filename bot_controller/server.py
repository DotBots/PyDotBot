#!/usr/bin/env python3


from bottle import run

# Examples curl -X POST -s -d '{"cmd": "aGVsbG8K"}' -H "Content-Type: application/json" http://localhost:8080/dotbot
# curl -X POST -s -d '{"cmd": "'$(base64 <<< azazazazazazaz)'"}' -H "Content-Type: application/json"
# http://localhost:8080/dotbot


# GW_TTY_PORT = os.getenv("GW_TTY_PORT", "COM9")
# GW_TTY_BAUDRATE = int(os.getenv("GW_TTY_BAUDRATE", 115200))


def start_server():
    run(host='0.0.0.0', port=8080)


if __name__ == "__main__":
    start_server()
