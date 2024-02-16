"""
For this script to work, you need to have a virtual serial port pair created. You can do this with socat:

```
socat -d -d pty,raw,echo=0 pty,raw,echo=0
```

It will output the paths to the created virtual serial ports, for example /dev/pts/74 and /dev/pts/75.

Then, start the dotbot-controller with -p /dev/pts/74, and run this script with /dev/pts/75 as the serial port.
"""

import serial, sys, lakers
import time

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

        if self.address == hex(payload.header.destination)[2:] and payload.payload_type == PayloadType.EDHOC_MESSAGE:
            print("received payload:", payload.values.value)
            return payload.values.value
        else:
            raise Exception("message not for me or not an edhoc message")

fb = FalsoBot("1234567890123456")


# values from traces-zeroconf.ipynb
ID_U = bytes.fromhex("a104412b")
G_W = bytes.fromhex("FFA4F102134029B3B156890B88C9D9619501196574174DCB68A07DB0588E4D41")
LOC_W = bytes.fromhex("636f61703a2f2f656e726f6c6c6d656e742e736572766572")
W = bytes.fromhex("4E5E15AB35008C15B89E91F9F329164D4AACD53D9923672CE0019F9ACD98573F")
KID_I = 0x2b
CRED_I = bytes.fromhex("A2027734322D35302D33312D46462D45462D33372D33322D333908A101A5010202412B2001215820AC75E9ECE3E50BFC8ED60399889522405C47BF16DF96660A41298CB4307F7EB62258206E5DE611388A4B8A8211334AC7D37ECB52A387D257E6DB3C2A93DF21FF3AFFC8")
I = bytes.fromhex("fb13adeb6518cee5f88417660841142e830a81fe334380a953406a1305e8706b")
CRED_V = bytes.fromhex("a2026b6578616d706c652e65647508a101a501020241322001215820bbc34960526ea4d32e940cad2a234148ddc21791a12afbcbac93622046dd44f02258204519e257236b2a0ce2023f0931f1f386ca7afda64fcde0108c224c51eabf6072")
V = bytes.fromhex("72cc4761dbd4c78f758931aa589d348d1ef874a7e303ede2f140dcf3e6aa4aac")
EAD_1_VALUE = bytes.fromhex("58287818636f61703a2f2f656e726f6c6c6d656e742e7365727665724dda9784962883c96ed01ff122c3")
MESSAGE_1_WITH_EAD = bytes.fromhex("0382060258208af6f430ebe18d34184017a9a11bf511c8dff8f834730b96c1b7c8dbca2fc3b6370158287818636f61703a2f2f656e726f6c6c6d656e742e7365727665724dda9784962883c96ed01ff122c3")
VOUCHER_RESPONSE = bytes.fromhex("8258520382060258208af6f430ebe18d34184017a9a11bf511c8dff8f834730b96c1b7c8dbca2fc3b6370158287818636f61703a2f2f656e726f6c6c6d656e742e7365727665724dda9784962883c96ed01ff122c34948c783671337f75bd5")
EAD_2_VALUE = bytes.fromhex("48c783671337f75bd5")

initiator = lakers.EdhocInitiator()
device = lakers.AuthzDevice(
    ID_U,
    G_W,
    LOC_W,
)

ead_1 = device.prepare_ead_1(
    initiator.compute_ephemeral_secret(device.get_g_w()),
    initiator.selected_cipher_suite(),
)
message_1 = initiator.prepare_message_1(c_i=None, ead_1=ead_1)
device.set_h_message_1(initiator.get_h_message_1())


with serial.Serial(sys.argv[1], timeout=1) as ser:
    print("sending msg1:", fb.edhoc_message(message_1))
    ser.write(fb.edhoc_message(message_1))
    while True:
        message_2 = ser.read(256)
        if len(message_2) > 0:
            message_2 = fb.parse_serial_input(message_2)
            break
    c_r, id_cred_r, ead_2 = initiator.parse_message_2(message_2)
    valid_cred_r = lakers.credential_check_or_fetch(id_cred_r, CRED_V)
    assert device.process_ead_2(ead_2, CRED_V)
    print(f"Authz voucher is valid!")
    initiator.verify_message_2(I, CRED_I, valid_cred_r)
    print(f"Message 2 is valid!")
    message_3, i_prk_out = initiator.prepare_message_3(lakers.CredentialTransfer.ByReference, None)
    ser.write(fb.edhoc_message(message_3))
    time.sleep(1)
    ser.write(fb.advertise())
    while True:
        pass
