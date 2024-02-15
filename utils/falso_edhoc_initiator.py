import serial

from dotbot.hdlc import hdlc_decode, hdlc_encode
from dotbot import GATEWAY_ADDRESS_DEFAULT, SWARM_ID_DEFAULT
from dotbot.hdlc import hdlc_decode, hdlc_encode
from dotbot.logger import LOGGER
from dotbot.protocol import (
    PROTOCOL_VERSION,
    Advertisement,
    EdhocMessage,
    ApplicationType,
    PayloadType,
    ProtocolHeader,
    ProtocolPayload,
)

class FalsoBot:
    def __init__(self, address):
        self.address = address

    @property
    def header(self):
        return ProtocolHeader(
            destination=int(GATEWAY_ADDRESS_DEFAULT, 16),
            source=int(self.address, 16),
            swarm_id=int(SWARM_ID_DEFAULT, 16),
            application=ApplicationType.DotBot,
            version=PROTOCOL_VERSION,
        )

    def advertise(self):
        payload = ProtocolPayload(
            self.header,
            PayloadType.ADVERTISEMENT,
            Advertisement(),
        )
        return hdlc_encode(payload.to_bytes())

    def edhoc_message(self, message):
        payload = ProtocolPayload(
            self.header,
            PayloadType.EDHOC_MESSAGE,
            EdhocMessage(value=message),
        )
        return hdlc_encode(payload.to_bytes())

    def parse_serial_input(self, frame):
        payload = ProtocolPayload.from_bytes(hdlc_decode(frame))

        if self.address == hex(payload.header.destination)[2:]:
            print("received payload:", payload.payload)

fb = FalsoBot("1234567890123456")

MESSAGE_1_WITH_EAD = bytes.fromhex("0382060258208af6f430ebe18d34184017a9a11bf511c8dff8f834730b96c1b7c8dbca2fc3b6370158287818636f61703a2f2f656e726f6c6c6d656e742e7365727665724dda9784962883c96ed01ff122c3")

with serial.Serial("/dev/pts/75", timeout=1) as ser:
    print("sending msg1:", fb.edhoc_message(MESSAGE_1_WITH_EAD))
    ser.write(fb.edhoc_message(MESSAGE_1_WITH_EAD))
    while True:
        msg2 = ser.read(256)
        if len(msg2) > 0:
            break
    #
