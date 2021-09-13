import serial
import threading

ser = serial.Serial()
ser.port = 'COM4'
ser.baudrate = 115200
ser.open()

def translate_cmd_vel(linear, angular):

    if linear == 0:
        if angular == 0:
            return b'0' # stop
        elif angular > 0:
            return b'4' # west
        else:
            return b'3' # east
    
    elif linear > 0:
        if angular == 0:
            return b'1' # north
        elif angular > 0:
            return b'5' # northeast
        else:
            return b'8' # northwest
    else:
        if angular == 0:
            return b'2' # south
        elif angular > 0:
            return b'6' # southeast
        else:
            return b'7' # southwest


def dotbot_serial(command):
    ser.write(command)


def command_move(linear, angular):
    serial_cmd = translate_cmd_vel(linear, angular)
    print(serial_cmd)
    dotbot_serial(serial_cmd)

def command_led(switch, color):
    pass

