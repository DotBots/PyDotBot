import serial
import shutil
import os
import time

# TODO: use logger instead of print statements

class Gateway:
    # TODO: load hex file from resources

    def __init__(self, port="COM4", baud=115200, open=True):
        self.ser = serial.Serial(port, baudrate=baud)
        if open:
            self.open()

    def open(self):
        if self.ser.isOpen():
            print("Port already open, quitting.") # TODO: logger warning
            return
        self.ser.open()

    def close(self):
        if not self.ser.isOpen():
            print("Port already closed, quitting.") # TODO: logger warning
            return
        self.ser.close()

    def dotbot_serial(self, command):
        if not self.ser.isOpen():
            print("Port already open, quitting.") # TODO: logger warning
            return False
        self.ser.write(command) # TODO: check if write is successful (also ack from dotbot)

        return True

    @staticmethod
    def translate_cmd_vel(linear, angular):
        """
        Note: This is for use prior to v2 of firmware where movement is continuous.
        :param linear:
        :param angular:
        :return:
        """
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

    def command_move(self, linear, angular):
        serial_cmd = Gateway.translate_cmd_vel(linear, angular)
        print(serial_cmd)
        return self.dotbot_serial(serial_cmd)

    def command_led(self, switch, color):
        pass

    @staticmethod
    def load_binary(bin_path, gateway_path):
        bin_size = os.path.getsize(bin_path)
        shutil.copy(bin_path, gateway_path)
        while True:
            time.sleep(2)
            sz = os.path.getsize(os.path.join(gateway_path, "Gateway-firmware_REL-0.1.hex"))
            print(sz)
            if bin_size >= sz: # TODO: verify acknowledgement from Gateway before returning from load_binary
                break

