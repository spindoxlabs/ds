from __future__ import annotations

import base64
import zlib
from typing import Any

from .crypto import generate_credential_id

BITSTRING_SIZE = 16384  # 16KB = 131072 bits


def create_bitstring() -> bytes:
    return b"\x00" * BITSTRING_SIZE


def set_bit(bitstring: bytes, index: int) -> bytes:
    ba = bytearray(bitstring)
    byte_index = index // 8
    bit_offset = 7 - (index % 8)
    ba[byte_index] |= 1 << bit_offset
    return bytes(ba)


def get_bit(bitstring: bytes, index: int) -> bool:
    byte_index = index // 8
    bit_offset = 7 - (index % 8)
    return bool(bitstring[byte_index] & (1 << bit_offset))


def encode_bitstring(bitstring: bytes) -> str:
    compressed = zlib.compress(bitstring)
    return base64.b64encode(compressed).decode()


def decode_bitstring(encoded: str) -> bytes:
    compressed = base64.b64decode(encoded)
    return zlib.decompress(compressed)


def next_available_index(bitstring: bytes) -> int:
    for i in range(BITSTRING_SIZE * 8):
        if not get_bit(bitstring, i):
            return i
    raise RuntimeError("Status list is full")


def build_status_list_credential(
    *,
    list_id: str,
    issuer_did: str,
    encoded_list: str,
    purpose: str = "revocation",
) -> dict[str, Any]:
    return {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://w3id.org/vc/status-list/2021/v1",
        ],
        "id": generate_credential_id(),
        "type": ["VerifiableCredential", "StatusList2021Credential"],
        "issuer": issuer_did,
        "credentialSubject": {
            "id": f"urn:status-list:{list_id}",
            "type": "StatusList2021",
            "statusPurpose": purpose,
            "encodedList": encoded_list,
        },
    }
