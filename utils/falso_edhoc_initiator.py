"""
For this script to work, you need to have a virtual serial port pair created. You can do this with socat:

```
socat -d -d pty,raw,echo=0 pty,raw,echo=0
```

It will output the paths to the created virtual serial ports, for example /dev/pts/74 and /dev/pts/75.

Then, start the dotbot-controller with -p /dev/pts/74, and run this script with /dev/pts/75 as the serial port.
"""

import sys
import time

import lakers
import serial

from dotbot import GATEWAY_ADDRESS_DEFAULT, SWARM_ID_DEFAULT
from dotbot.hdlc import hdlc_decode, hdlc_encode
from dotbot.protocol import (
    PROTOCOL_VERSION,
    Advertisement,
    ApplicationType,
    EdhocMessage,
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

        if self.address == hex(payload.header.destination)[2:] and payload.payload_type == PayloadType.EDHOC_MESSAGE:
            print("received payload:", payload.values.value)
            return payload.values.value
        else:
            raise Exception("message not for me or not an edhoc message")


class EdhocBot:
    def __init__(self, I, CRED_I, ID_U, G_W, LOC_W):
        self.initiator = lakers.EdhocInitiator()
        self.device = lakers.AuthzDevice(ID_U, G_W, LOC_W)
        self.fb = FalsoBot(ID_U.hex())
        self.ID_U = ID_U
        self.I = I
        self.CRED_I = CRED_I

    def run_handshake(self, ser):
        print(f"Starting EDHOC handshake with ID_U={self.ID_U.hex()}")
        ead_1 = self.device.prepare_ead_1(
            self.initiator.compute_ephemeral_secret(self.device.get_g_w()),
            self.initiator.selected_cipher_suite(),
        )
        message_1 = self.initiator.prepare_message_1(c_i=None, ead_1=ead_1)
        self.device.set_h_message_1(self.initiator.get_h_message_1())

        print("sending msg1:", self.fb.edhoc_message(message_1))
        ser.write(self.fb.edhoc_message(message_1))
        while True:
            message_2 = ser.read(256)
            if len(message_2) > 0:
                message_2 = self.fb.parse_serial_input(message_2)
                break
        c_r, id_cred_r, ead_2 = self.initiator.parse_message_2(message_2)
        valid_cred_r = lakers.credential_check_or_fetch(id_cred_r, None)
        assert self.device.process_ead_2(ead_2, valid_cred_r)
        print("Authz voucher is valid!")
        self.initiator.verify_message_2(self.I, self.CRED_I, valid_cred_r)
        print("Message 2 is valid!")
        message_3, i_prk_out = self.initiator.prepare_message_3(lakers.CredentialTransfer.ByReference, None)
        ser.write(self.fb.edhoc_message(message_3))
        time.sleep(1)
        ser.write(self.fb.advertise())
        print("sent msg3 and advertise")

# open serial port
ser = serial.Serial(sys.argv[1], timeout=1)

# values from traces-zeroconf.ipynb
ID_U = bytes.fromhex("a104412b")
G_W = bytes.fromhex("FFA4F102134029B3B156890B88C9D9619501196574174DCB68A07DB0588E4D41")
LOC_W = "http://localhost:18000"

CRED_I = bytes.fromhex("A2027734322D35302D33312D46462D45462D33372D33322D333908A101A5010202412B2001215820AC75E9ECE3E50BFC8ED60399889522405C47BF16DF96660A41298CB4307F7EB62258206E5DE611388A4B8A8211334AC7D37ECB52A387D257E6DB3C2A93DF21FF3AFFC8")
I = bytes.fromhex("fb13adeb6518cee5f88417660841142e830a81fe334380a953406a1305e8706b")

edhoc_bots = [
    EdhocBot(
        I, CRED_I,
        bytes.fromhex("a104412b"), G_W, LOC_W,
    ),
    EdhocBot(
        I, CRED_I,
        bytes.fromhex("a104413c"), G_W, LOC_W,
    )
]

for edhoc_bot in edhoc_bots:
    print("==== starting handshake ====")
    edhoc_bot.run_handshake(ser)
