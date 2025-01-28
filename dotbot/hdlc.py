# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module implementing HDLC protocol primitives."""

from enum import Enum

from dotbot.logger import LOGGER

HDLC_FLAG = b"\x7e"
HDLC_FLAG_ESCAPED = b"\x5e"
HDLC_ESCAPE = b"\x7d"
HDLC_ESCAPE_ESCAPED = b"\x5d"
HDLC_FCS_INIT = 0xFFFF
HDLC_FCS_OK = 0xF0B8

# fmt: off
FCS16TAB = (
    0x0000, 0x1189, 0x2312, 0x329B, 0x4624, 0x57AD, 0x6536, 0x74BF,
    0x8C48, 0x9DC1, 0xAF5A, 0xBED3, 0xCA6C, 0xDBE5, 0xE97E, 0xF8F7,
    0x1081, 0x0108, 0x3393, 0x221A, 0x56A5, 0x472C, 0x75B7, 0x643E,
    0x9CC9, 0x8D40, 0xBFDB, 0xAE52, 0xDAED, 0xCB64, 0xF9FF, 0xE876,
    0x2102, 0x308B, 0x0210, 0x1399, 0x6726, 0x76AF, 0x4434, 0x55BD,
    0xAD4A, 0xBCC3, 0x8E58, 0x9FD1, 0xEB6E, 0xFAE7, 0xC87C, 0xD9F5,
    0x3183, 0x200A, 0x1291, 0x0318, 0x77A7, 0x662E, 0x54B5, 0x453C,
    0xBDCB, 0xAC42, 0x9ED9, 0x8F50, 0xFBEF, 0xEA66, 0xD8FD, 0xC974,
    0x4204, 0x538D, 0x6116, 0x709F, 0x0420, 0x15A9, 0x2732, 0x36BB,
    0xCE4C, 0xDFC5, 0xED5E, 0xFCD7, 0x8868, 0x99E1, 0xAB7A, 0xBAF3,
    0x5285, 0x430C, 0x7197, 0x601E, 0x14A1, 0x0528, 0x37B3, 0x263A,
    0xDECD, 0xCF44, 0xFDDF, 0xEC56, 0x98E9, 0x8960, 0xBBFB, 0xAA72,
    0x6306, 0x728F, 0x4014, 0x519D, 0x2522, 0x34AB, 0x0630, 0x17B9,
    0xEF4E, 0xFEC7, 0xCC5C, 0xDDD5, 0xA96A, 0xB8E3, 0x8A78, 0x9BF1,
    0x7387, 0x620E, 0x5095, 0x411C, 0x35A3, 0x242A, 0x16B1, 0x0738,
    0xFFCF, 0xEE46, 0xDCDD, 0xCD54, 0xB9EB, 0xA862, 0x9AF9, 0x8B70,
    0x8408, 0x9581, 0xA71A, 0xB693, 0xC22C, 0xD3A5, 0xE13E, 0xF0B7,
    0x0840, 0x19C9, 0x2B52, 0x3ADB, 0x4E64, 0x5FED, 0x6D76, 0x7CFF,
    0x9489, 0x8500, 0xB79B, 0xA612, 0xD2AD, 0xC324, 0xF1BF, 0xE036,
    0x18C1, 0x0948, 0x3BD3, 0x2A5A, 0x5EE5, 0x4F6C, 0x7DF7, 0x6C7E,
    0xA50A, 0xB483, 0x8618, 0x9791, 0xE32E, 0xF2A7, 0xC03C, 0xD1B5,
    0x2942, 0x38CB, 0x0A50, 0x1BD9, 0x6F66, 0x7EEF, 0x4C74, 0x5DFD,
    0xB58B, 0xA402, 0x9699, 0x8710, 0xF3AF, 0xE226, 0xD0BD, 0xC134,
    0x39C3, 0x284A, 0x1AD1, 0x0B58, 0x7FE7, 0x6E6E, 0x5CF5, 0x4D7C,
    0xC60C, 0xD785, 0xE51E, 0xF497, 0x8028, 0x91A1, 0xA33A, 0xB2B3,
    0x4A44, 0x5BCD, 0x6956, 0x78DF, 0x0C60, 0x1DE9, 0x2F72, 0x3EFB,
    0xD68D, 0xC704, 0xF59F, 0xE416, 0x90A9, 0x8120, 0xB3BB, 0xA232,
    0x5AC5, 0x4B4C, 0x79D7, 0x685E, 0x1CE1, 0x0D68, 0x3FF3, 0x2E7A,
    0xE70E, 0xF687, 0xC41C, 0xD595, 0xA12A, 0xB0A3, 0x8238, 0x93B1,
    0x6B46, 0x7ACF, 0x4854, 0x59DD, 0x2D62, 0x3CEB, 0x0E70, 0x1FF9,
    0xF78F, 0xE606, 0xD49D, 0xC514, 0xB1AB, 0xA022, 0x92B9, 0x8330,
    0x7BC7, 0x6A4E, 0x58D5, 0x495C, 0x3DE3, 0x2C6A, 0x1EF1, 0x0F78,
)
# fmt: on


class HDLCDecodeException(Exception):
    """Exception raised when decoding wrong HDLC frames."""


def _fcs_update(fcs, byte):
    return (fcs >> 8) ^ FCS16TAB[((fcs ^ ord(byte)) & 0xFF)]


def _to_byte(value):
    return int(value).to_bytes(1, "little")


def _escape_byte(byte) -> bytes:
    result = bytearray()
    if byte == HDLC_ESCAPE:
        result += HDLC_ESCAPE
        result += HDLC_ESCAPE_ESCAPED
    elif byte == HDLC_FLAG:
        result += HDLC_ESCAPE
        result += HDLC_FLAG_ESCAPED
    else:
        result += byte
    return result


def hdlc_encode(payload: bytes) -> bytes:
    """Encodes a payload in an HDLC frame.
    >>> hdlc_encode(b"test")
    bytearray(b'~test\\x88\\x07~')
    >>> hdlc_encode(b"")
    bytearray(b'~\\x00\\x00~')
    >>> hdlc_encode(b"\\x00\\x00\\xf6\\xf6\\xf6\\xf6")
    bytearray(b'~\\x00\\x00\\xf6\\xf6\\xf6\\xf6\\xb2+~')
    >>> hdlc_encode(b"\\x00\\x01\\n\\n\\n")
    bytearray(b'~\\x00\\x01\\n\\n\\n\\x9c\\xf2~')
    >>> hdlc_encode(b"~test~")
    bytearray(b'~}^test}^\\x9d\\xa6~')
    >>> hdlc_encode(b"~test}")
    bytearray(b'~}^test}]\\x06\\x94~')
    >>> hdlc_encode(b"\\xe7\\x94:\\xa6")
    bytearray(b'~\\xe7\\x94:\\xa6\\x83}^~')
    >>> hdlc_encode(b"'$W\\x82")
    bytearray(b"~\\'$W\\x82\\x13}]~")
    """
    # initialize output buffer
    hdlc_frame = bytearray()

    # initialize frame check sequence
    fcs = HDLC_FCS_INIT

    # add start flag
    hdlc_frame += HDLC_FLAG

    # write payload in frame
    for byte in payload:
        fcs = _fcs_update(fcs, _to_byte(byte))
        hdlc_frame += _escape_byte(_to_byte(byte))
    fcs = 0xFFFF - fcs

    # add FCS
    hdlc_frame += _escape_byte(_to_byte(fcs & 0xFF))
    hdlc_frame += _escape_byte(_to_byte((fcs & 0xFF00) >> 8))

    # add end flag
    hdlc_frame += HDLC_FLAG

    return hdlc_frame


def hdlc_decode(frame: bytes) -> bytes:
    """Decodes an HDLC frame and return the payload it contains.

    >>> hdlc_decode(b"~test\\x88\\x07~")
    bytearray(b'test')
    >>> hdlc_decode(b"~\\x00\\x00\\xf6\\xf6\\xf6\\xf6\\xb2+~")
    bytearray(b'\\x00\\x00\\xf6\\xf6\\xf6\\xf6')
    >>> hdlc_decode(b"~\\x00\\x01\\n\\n\\n\\x9c\\xf2~")
    bytearray(b'\\x00\\x01\\n\\n\\n')
    >>> hdlc_decode(b"~}^test}^\\x9d\\xa6~")
    bytearray(b'~test~')
    >>> hdlc_decode(b"~}^test}]\\x06\\x94~")
    bytearray(b'~test}')
    >>> hdlc_decode(b"~\\xe7\\x94:\\xa6\\x83}^~")
    bytearray(b'\\xe7\\x94:\\xa6')
    >>> hdlc_decode(b"~\\'$W\\x82\\x13}]~")
    bytearray(b"\\'$W\\x82")
    >>> hdlc_decode(b"~\\x00\\x00~")
    bytearray(b'')
    >>> hdlc_decode(b"~test\\x42\\x42~")
    Traceback (most recent call last):
    dotbot.hdlc.HDLCDecodeException: Invalid FCS
    >>> hdlc_decode(b"~\\x00~")
    Traceback (most recent call last):
    dotbot.hdlc.HDLCDecodeException: Invalid payload
    """
    output = bytearray()
    fcs = HDLC_FCS_INIT
    escape_byte = False
    for byte in frame[1:-1]:
        byte = _to_byte(byte)
        if byte == HDLC_ESCAPE:
            escape_byte = True
        elif escape_byte is True:
            if byte == HDLC_ESCAPE_ESCAPED:
                output += HDLC_ESCAPE
                fcs = _fcs_update(fcs, HDLC_ESCAPE)
            elif byte == HDLC_FLAG_ESCAPED:
                output += HDLC_FLAG
                fcs = _fcs_update(fcs, HDLC_FLAG)
            escape_byte = False
        else:
            output += byte
            fcs = _fcs_update(fcs, byte)
    if len(output) < 2:
        raise HDLCDecodeException("Invalid payload")
    if fcs != HDLC_FCS_OK:
        raise HDLCDecodeException("Invalid FCS")
    return output[:-2]


class HDLCState(Enum):
    """State of the HDLC handler."""

    IDLE = 0
    RECEIVING = 1
    READY = 2


class HDLCHandler:
    """Handles the reception of an HDLC frame byte by byte."""

    def __init__(self):
        self.state = HDLCState.IDLE
        self.fcs = HDLC_FCS_INIT
        self.output = bytearray()
        self.escape_byte = False
        self._logger = LOGGER.bind(context=__name__)

    @property
    def payload(self):
        """Returns the payload contained in a frame."""
        if self.state != HDLCState.READY:
            raise HDLCDecodeException("Incomplete HDLC frame")

        self.state = HDLCState.IDLE
        if len(self.output) < 2:
            self._logger.error("Invalid payload")
            return bytearray()
        if self.fcs != HDLC_FCS_OK:
            self._logger.error("Invalid FCS")
            return bytearray()
        self.fcs = HDLC_FCS_INIT
        return self.output[:-2]

    def handle_byte(self, byte):
        """Handle new byte received."""
        if self.state in [HDLCState.IDLE, HDLCState.READY] and byte == HDLC_FLAG:
            self.output = bytearray()
            self.fcs = HDLC_FCS_INIT
            self.state = HDLCState.RECEIVING
        elif self.output and self.state == HDLCState.RECEIVING and byte == HDLC_FLAG:
            # End of frame
            self.state = HDLCState.READY
        elif self.state == HDLCState.RECEIVING and byte != HDLC_FLAG:
            # Middle of the frame
            if byte == HDLC_ESCAPE:
                self.escape_byte = True
            elif self.escape_byte is True:
                if byte == HDLC_ESCAPE_ESCAPED:
                    self.output += HDLC_ESCAPE
                    self.fcs = _fcs_update(self.fcs, HDLC_ESCAPE)
                elif byte == HDLC_FLAG_ESCAPED:
                    self.output += HDLC_FLAG
                    self.fcs = _fcs_update(self.fcs, HDLC_FLAG)
                self.escape_byte = False
            else:
                self.output += byte
                self.fcs = _fcs_update(self.fcs, byte)
