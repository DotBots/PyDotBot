import base64
import serial
from bottle import post, request


@post('/dotbot')
def dotbot(serial_baudrate: int, serial_port: str):
    message = base64.b64decode(request.json["cmd"])
    with serial.Serial(serial_baudrate, serial_port, timeout=1) as ser:
        ser.write(len(message).to_bytes(1, 'little'))
        ser.write(message)
