"""`dcp-trust` reads a status list's `encodedList` in both encodings.

The identity registry moved from StatusList2021 (plain base64) to Bitstring
Status List (multibase: `u` + base64url, no padding). Both are GZIP.
"""

from __future__ import annotations

import base64
import gzip

from ds_e2e.flows.dcp_trust import decode_encoded_list

BITS = gzip.compress(bytes(16384))


def test_plain_base64_is_read():
    assert decode_encoded_list(base64.b64encode(BITS).decode()) == BITS


def test_multibase_base64url_without_padding_is_read():
    encoded = "u" + base64.urlsafe_b64encode(BITS).decode().rstrip("=")
    raw = decode_encoded_list(encoded)
    assert raw == BITS
    assert raw[:2] == b"\x1f\x8b"


def test_a_urlsafe_character_survives():
    payload = b"\xfb\xff\xfe" * 7
    encoded = "u" + base64.urlsafe_b64encode(payload).decode().rstrip("=")
    assert "-" in encoded or "_" in encoded
    assert decode_encoded_list(encoded) == payload
