"""Crypto functions for MQTT with crypto mode."""

import base64
from random import randint

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from joserfc import jwe

from dotbot.protocol import PROTOCOL_VERSION

PIN_CODE_SIZE = 8
JOSE_PROTECTED = {"alg": "dir", "enc": "A256GCM"}


def generate_pin_code() -> int:
    return randint(10 ** (PIN_CODE_SIZE - 1), 10**PIN_CODE_SIZE - 1)


def derive_topic(pin_code: int) -> str:
    """Derive a topic from a pin code."""
    kdf_topic = HKDF(
        algorithm=hashes.SHA256(),
        length=16,
        salt=b"",
        info=f"secret_topic_{PROTOCOL_VERSION}".encode(),
    )
    topic = kdf_topic.derive(str(pin_code).encode())
    return base64.urlsafe_b64encode(topic).decode()


def derive_aes_key(pin_code: int) -> bytes:
    """Derive an AES key from a pin code."""
    kdf_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"",
        info=f"secret_key_{PROTOCOL_VERSION}".encode(),
    )
    return kdf_key.derive(str(pin_code).encode())


def encrypt(data: str, key: bytes) -> str:
    """Encrypt data with AES-GCM."""
    return jwe.encrypt_compact(JOSE_PROTECTED, data, key)


def decrypt(data: str, key: bytes) -> str:
    """Decrypt data with AES-GCM."""
    return jwe.decrypt_compact(data, key).plaintext.decode()
