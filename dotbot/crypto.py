"""Crypto functions for MQTT with crypto mode."""

import base64
import os
from typing import List

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from dotbot.protocol import PROTOCOL_VERSION


def get_topic(pin_code: int) -> str:
    """Derive a topic from a pin code."""
    kdf_topic = HKDF(
        algorithm=hashes.SHA256(),
        length=16,
        salt=b"",
        info=f"secret_topic_{PROTOCOL_VERSION}".encode(),
    )
    topic = kdf_topic.derive(str(pin_code).encode())
    return base64.urlsafe_b64encode(topic).decode()


def get_aes_key(pin_code: int) -> bytes:
    """Derive an AES key from a pin code."""
    kdf_key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"",
        info=f"secret_key_{PROTOCOL_VERSION}".encode(),
    )
    key = kdf_key.derive(str(pin_code).encode())
    return key


def encrypt(data: bytes, key: bytes) -> List[bytes]:
    """Encrypt data with AES-GCM."""
    aad = str(PROTOCOL_VERSION).encode()
    aesgcm = AESGCM(key)
    nonce = os.urandom(16)
    encrypted = aesgcm.encrypt(nonce, data, aad)
    return base64.b64encode(encrypted), nonce


def decrypt(data: str, key, nonce: bytes) -> bytes:
    """Decrypt data with AES-GCM."""
    aad = str(PROTOCOL_VERSION).encode()
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, data, aad).decode()
    except Exception as exc:
        print(exc)
        return b""
