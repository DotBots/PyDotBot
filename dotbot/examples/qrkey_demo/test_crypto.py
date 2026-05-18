# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Pin the qrkey crypto contract from PyDotBot's perspective.

The qrkey package owns crypto correctness (its own test suite covers
HKDF + AES-GCM). PyDotBot only needs to guarantee that whichever qrkey
version it depends on keeps producing the same keys and topics as
qrkey 0.12.1, so phones holding existing QR codes can still connect.
"""

from qrkey.crypto import derive_aes_key, derive_topic

GOLDEN_PIN = "123456789012"


def test_qrkey_crypto_matches_0_12_1_baseline():
    assert derive_aes_key(GOLDEN_PIN).hex() == (
        "fd420ec85ae026021eabf174cbd594835f463d617443222e5f19aac6787c7bd7"
    )
    assert derive_topic(GOLDEN_PIN) == "AjHghGOlWfMoUEfaJVm9yw=="
