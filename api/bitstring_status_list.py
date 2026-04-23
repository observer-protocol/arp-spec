"""
Bitstring Status List v1.0 — encode/decode/verify utilities.

Implements the W3C Bitstring Status List v1.0 Recommendation (May 2025).

Encoding chain per spec: raw bitstring -> GZIP compress -> base64url encode.
Minimum bitstring size: 131,072 bits (16 KB uncompressed, ~16 bytes compressed
when all zeros).

This module handles the bitstring manipulation only. Credential wrapping
(constructing the BitstringStatusListCredential VC) is handled by the caller.
"""

import base64
import gzip
import math
from typing import Optional


# W3C minimum: 131,072 bits = 16,384 bytes
MINIMUM_BITSTRING_SIZE = 131_072
DEFAULT_BITSTRING_SIZE = MINIMUM_BITSTRING_SIZE


def create_bitstring(size: int = DEFAULT_BITSTRING_SIZE) -> bytearray:
    """
    Create a new bitstring of the given size (in bits), all zeros.

    Args:
        size: Number of bits. Must be >= MINIMUM_BITSTRING_SIZE.

    Returns:
        A bytearray of ceil(size/8) bytes, all zeros.

    Raises:
        ValueError: If size is below the W3C minimum.
    """
    if size < MINIMUM_BITSTRING_SIZE:
        raise ValueError(
            f"Bitstring size must be at least {MINIMUM_BITSTRING_SIZE} bits, got {size}"
        )
    num_bytes = math.ceil(size / 8)
    return bytearray(num_bytes)


def encode_bitstring(raw: bytearray) -> str:
    """
    Encode a raw bitstring per Bitstring Status List v1.0:
    raw bytes -> GZIP compress -> base64url encode (no padding).

    Args:
        raw: The raw bitstring as a bytearray.

    Returns:
        Base64url-encoded string (no padding) of the GZIP-compressed bitstring.
    """
    compressed = gzip.compress(bytes(raw))
    return base64.urlsafe_b64encode(compressed).rstrip(b"=").decode("ascii")


def decode_bitstring(encoded: str) -> bytearray:
    """
    Decode a Bitstring Status List v1.0 encoded string back to raw bytes.
    base64url decode -> GZIP decompress -> raw bytes.

    Args:
        encoded: Base64url-encoded string (with or without padding).

    Returns:
        The raw bitstring as a bytearray.

    Raises:
        ValueError: If decoding or decompression fails.
    """
    # Add padding if needed
    padded = encoded + "=" * (4 - len(encoded) % 4) if len(encoded) % 4 else encoded
    try:
        compressed = base64.urlsafe_b64decode(padded)
    except Exception as exc:
        raise ValueError(f"Base64url decode failed: {exc}") from exc

    try:
        raw = gzip.decompress(compressed)
    except Exception as exc:
        raise ValueError(f"GZIP decompress failed: {exc}") from exc

    return bytearray(raw)


def get_bit(raw: bytearray, index: int) -> int:
    """
    Get the value of a specific bit in the bitstring.

    Bit ordering per W3C spec: bit 0 is the most significant bit of byte 0.
    Index i maps to byte i//8, bit (7 - i%8).

    Args:
        raw: The raw bitstring.
        index: The bit index (0-based).

    Returns:
        0 or 1.

    Raises:
        IndexError: If index is out of range.
    """
    total_bits = len(raw) * 8
    if index < 0 or index >= total_bits:
        raise IndexError(f"Bit index {index} out of range [0, {total_bits})")
    byte_idx = index // 8
    bit_offset = 7 - (index % 8)
    return (raw[byte_idx] >> bit_offset) & 1


def set_bit(raw: bytearray, index: int, value: int) -> None:
    """
    Set the value of a specific bit in the bitstring.

    Args:
        raw: The raw bitstring (modified in place).
        index: The bit index (0-based).
        value: 0 or 1.

    Raises:
        IndexError: If index is out of range.
        ValueError: If value is not 0 or 1.
    """
    if value not in (0, 1):
        raise ValueError(f"Bit value must be 0 or 1, got {value}")
    total_bits = len(raw) * 8
    if index < 0 or index >= total_bits:
        raise IndexError(f"Bit index {index} out of range [0, {total_bits})")
    byte_idx = index // 8
    bit_offset = 7 - (index % 8)
    if value:
        raw[byte_idx] |= (1 << bit_offset)
    else:
        raw[byte_idx] &= ~(1 << bit_offset)


def diff_bitstrings(old_raw: bytearray, new_raw: bytearray) -> dict[int, tuple[int, int]]:
    """
    Find all bit positions that changed between two bitstrings.

    Args:
        old_raw: The previous bitstring.
        new_raw: The new bitstring.

    Returns:
        Dict mapping bit index -> (old_value, new_value) for each changed bit.

    Raises:
        ValueError: If bitstrings have different lengths.
    """
    if len(old_raw) != len(new_raw):
        raise ValueError(
            f"Bitstring length mismatch: {len(old_raw)} vs {len(new_raw)} bytes"
        )

    changes = {}
    for byte_idx in range(len(old_raw)):
        if old_raw[byte_idx] == new_raw[byte_idx]:
            continue
        xor = old_raw[byte_idx] ^ new_raw[byte_idx]
        for bit_offset in range(8):
            if xor & (1 << (7 - bit_offset)):
                bit_index = byte_idx * 8 + bit_offset
                old_val = (old_raw[byte_idx] >> (7 - bit_offset)) & 1
                new_val = (new_raw[byte_idx] >> (7 - bit_offset)) & 1
                changes[bit_index] = (old_val, new_val)

    return changes


def validate_status_list_update(
    old_encoded: str,
    new_encoded: str,
    status_purpose: str,
) -> tuple[bool, str, dict[int, tuple[int, int]]]:
    """
    Validate a status list update against protocol rules.

    Rules:
      - For statusPurpose "revocation": bits may only change 0->1 (no un-revocation).
      - For statusPurpose "suspension": bits may change in either direction.
      - Bitstring lengths must match.

    Args:
        old_encoded: The current encoded bitstring.
        new_encoded: The proposed new encoded bitstring.
        status_purpose: "revocation" or "suspension".

    Returns:
        (True, "ok", changes_dict) if valid.
        (False, "<reason>", changes_dict) if invalid.
    """
    try:
        old_raw = decode_bitstring(old_encoded)
        new_raw = decode_bitstring(new_encoded)
    except ValueError as exc:
        return False, f"Bitstring decode error: {exc}", {}

    if len(old_raw) != len(new_raw):
        return False, f"Bitstring size mismatch: {len(old_raw)} vs {len(new_raw)} bytes", {}

    changes = diff_bitstrings(old_raw, new_raw)

    if not changes:
        return False, "No bits changed in the update", {}

    if status_purpose == "revocation":
        reversals = {idx: vals for idx, vals in changes.items() if vals == (1, 0)}
        if reversals:
            indices = sorted(reversals.keys())
            return False, f"Revocation is terminal: cannot flip bits back to 0 at indices {indices}", changes

    return True, "ok", changes
