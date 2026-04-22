"""
Bitstring Status List v1.0 Utilities
Spec: Spec 3.3 — Revocation and Lifecycle (Phase 3, Capability 3)

This module provides encode/decode/verify utilities for W3C Bitstring Status List v1.0.
The bitstring is a compressed, base64-encoded representation of credential statuses.

Encoding chain: raw bytes -> GZIP -> base64
Default size: 131,072 bits (16KB uncompressed)

Reference: https://www.w3.org/TR/vc-bitstring-status-list/
"""

import gzip
import base64
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

# Default bitstring size per W3C spec: 131,072 bits = 16KB uncompressed
DEFAULT_BITSTRING_SIZE = 131072


def create_empty_bitstring(size: int = DEFAULT_BITSTRING_SIZE) -> bytes:
    """
    Create a new bitstring of all zeros.
    
    Args:
        size: Number of bits in the bitstring (default 131072)
        
    Returns:
        bytes: All-zero bitstring (size // 8 bytes)
    """
    if size % 8 != 0:
        raise ValueError(f"Bitstring size must be divisible by 8, got {size}")
    return bytes(size // 8)


def set_bit(bitstring: bytes, index: int, value: bool) -> bytes:
    """
    Set bit at index to 0 or 1. Returns new bytes.
    
    Args:
        bitstring: The current bitstring bytes
        index: Bit index (0-based)
        value: True to set bit to 1, False to set to 0
        
    Returns:
        bytes: New bitstring with bit set
        
    Raises:
        IndexError: If index is out of range
    """
    if index < 0 or index >= len(bitstring) * 8:
        raise IndexError(f"Bit index {index} out of range for bitstring of size {len(bitstring) * 8}")
    
    # Calculate byte and bit position
    byte_idx = index // 8
    bit_idx = index % 8
    
    # Convert to mutable list
    byte_list = list(bitstring)
    
    if value:
        # Set bit to 1
        byte_list[byte_idx] |= (1 << bit_idx)
    else:
        # Set bit to 0
        byte_list[byte_idx] &= ~(1 << bit_idx)
    
    return bytes(byte_list)


def get_bit(bitstring: bytes, index: int) -> bool:
    """
    Get bit value at index.
    
    Args:
        bitstring: The bitstring bytes
        index: Bit index (0-based)
        
    Returns:
        bool: True if bit is set (1), False if not (0)
        
    Raises:
        IndexError: If index is out of range
    """
    if index < 0 or index >= len(bitstring) * 8:
        raise IndexError(f"Bit index {index} out of range for bitstring of size {len(bitstring) * 8}")
    
    byte_idx = index // 8
    bit_idx = index % 8
    
    return bool(bitstring[byte_idx] & (1 << bit_idx))


def encode_bitstring(bitstring: bytes) -> str:
    """
    Compress and base64-encode: raw -> GZIP -> base64
    
    Per W3C Bitstring Status List v1.0 spec:
    - Compress using GZIP
    - Encode using base64 (standard, not URL-safe)
    
    Args:
        bitstring: Raw bitstring bytes
        
    Returns:
        str: Base64-encoded compressed bitstring
    """
    compressed = gzip.compress(bitstring)
    return base64.b64encode(compressed).decode('ascii')


def decode_bitstring(encoded: str) -> bytes:
    """
    Decode and decompress: base64 -> GZIP -> raw
    
    Per W3C Bitstring Status List v1.0 spec:
    - Decode from base64
    - Decompress using GZIP
    
    Args:
        encoded: Base64-encoded compressed bitstring
        
    Returns:
        bytes: Raw bitstring bytes
        
    Raises:
        ValueError: If decoding or decompression fails
    """
    try:
        compressed = base64.b64decode(encoded)
        return gzip.decompress(compressed)
    except Exception as e:
        raise ValueError(f"Failed to decode bitstring: {e}")


def get_changed_bits(old_bitstring: bytes, new_bitstring: bytes) -> List[Dict[str, Any]]:
    """
    Identify which bits changed between two bitstrings.
    
    Args:
        old_bitstring: Previous bitstring state
        new_bitstring: New bitstring state
        
    Returns:
        List of dicts with 'index', 'old_value', 'new_value' for each changed bit
        
    Raises:
        ValueError: If bitstrings have different lengths
    """
    if len(old_bitstring) != len(new_bitstring):
        raise ValueError(f"Bitstrings must have same length: {len(old_bitstring)} != {len(new_bitstring)}")
    
    changes = []
    total_bits = len(old_bitstring) * 8
    
    for index in range(total_bits):
        old_val = get_bit(old_bitstring, index)
        new_val = get_bit(new_bitstring, index)
        if old_val != new_val:
            changes.append({
                'index': index,
                'old_value': old_val,
                'new_value': new_val
            })
    
    return changes


def create_status_list_credential(
    issuer_did: str,
    status_list_id: str,
    status_list_url: str,
    encoded_bitstring: str,
    status_purpose: str,
    signing_key_id: Optional[str] = None,
    valid_from: Optional[datetime] = None,
    valid_until: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Create a BitstringStatusListCredential VC structure.
    
    This creates the credential structure. The proof must be added separately
    by signing with the issuer's key (OP never signs - "OP hosts bytes, never keys").
    
    Args:
        issuer_did: DID of the status list issuer
        status_list_id: Unique identifier for this status list
        status_list_url: Public URL where this credential will be hosted
        encoded_bitstring: GZIP-compressed, base64-encoded bitstring
        status_purpose: 'revocation' or 'suspension'
        signing_key_id: Specific key ID to use (defaults to issuer_did + '#key-1')
        valid_from: Validity start time (defaults to now)
        valid_until: Validity end time (defaults to 1 year from now)
        
    Returns:
        dict: BitstringStatusListCredential structure (without proof - must be signed)
    """
    if status_purpose not in ('revocation', 'suspension'):
        raise ValueError(f"status_purpose must be 'revocation' or 'suspension', got {status_purpose}")
    
    if valid_from is None:
        valid_from = datetime.now(timezone.utc)
    if valid_until is None:
        # Default 1 year validity
        from datetime import timedelta
        valid_until = valid_from + timedelta(days=365)
    
    if signing_key_id is None:
        signing_key_id = f"{issuer_did}#key-1"
    
    credential = {
        "@context": [
            "https://www.w3.org/ns/credentials/v2",
            "https://www.w3.org/ns/credentials/status-list/v1"
        ],
        "id": status_list_url,
        "type": ["VerifiableCredential", "BitstringStatusListCredential"],
        "issuer": issuer_did,
        "validFrom": valid_from.isoformat().replace('+00:00', 'Z'),
        "validUntil": valid_until.isoformat().replace('+00:00', 'Z'),
        "credentialSubject": {
            "id": f"{status_list_url}#list",
            "type": "BitstringStatusList",
            "statusPurpose": status_purpose,
            "encodedList": encoded_bitstring
        }
    }
    
    return credential


def validate_status_list_credential(credential: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate the structure of a BitstringStatusListCredential.
    
    This validates structure only, not signature. Use crypto_verification for signature checks.
    
    Args:
        credential: The credential to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Check required top-level fields
    required_fields = ['@context', 'id', 'type', 'issuer', 'validFrom', 'credentialSubject']
    for field in required_fields:
        if field not in credential:
            return False, f"Missing required field: {field}"
    
    # Check context
    context = credential.get('@context', [])
    if not isinstance(context, list):
        return False, "@context must be an array"
    if "https://www.w3.org/ns/credentials/v2" not in context:
        return False, "Missing W3C VC v2 context"
    if "https://www.w3.org/ns/credentials/status-list/v1" not in context:
        return False, "Missing Bitstring Status List context"
    
    # Check type
    types = credential.get('type', [])
    if not isinstance(types, list):
        return False, "type must be an array"
    if "VerifiableCredential" not in types:
        return False, "Missing VerifiableCredential type"
    if "BitstringStatusListCredential" not in types:
        return False, "Missing BitstringStatusListCredential type"
    
    # Check credentialSubject
    subject = credential.get('credentialSubject', {})
    if not isinstance(subject, dict):
        return False, "credentialSubject must be an object"
    
    required_subject_fields = ['id', 'type', 'statusPurpose', 'encodedList']
    for field in required_subject_fields:
        if field not in subject:
            return False, f"credentialSubject missing required field: {field}"
    
    # Check statusPurpose
    purpose = subject.get('statusPurpose')
    if purpose not in ('revocation', 'suspension'):
        return False, f"statusPurpose must be 'revocation' or 'suspension', got {purpose}"
    
    # Check encodedList is valid base64
    encoded = subject.get('encodedList', '')
    try:
        decoded = decode_bitstring(encoded)
        # Verify it's a reasonable size (divisible by 8 for bits)
        if len(decoded) * 8 < 1:
            return False, "Decoded bitstring is empty"
    except Exception as e:
        return False, f"Invalid encodedList (must be base64-encoded GZIP): {e}"
    
    return True, "Valid BitstringStatusListCredential structure"


def extract_credential_status(credential: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract credentialStatus entries from a credential.
    
    Args:
        credential: A Verifiable Credential
        
    Returns:
        List of credentialStatus entries (may be empty)
    """
    status = credential.get('credentialStatus')
    if not status:
        return []
    
    if isinstance(status, dict):
        return [status]
    elif isinstance(status, list):
        return status
    else:
        return []


def check_credential_in_status_list(
    credential_status: Dict[str, Any],
    status_list_credential: Dict[str, Any]
) -> tuple[bool, Optional[str]]:
    """
    Check if a credential is revoked/suspended based on its status list.
    
    Args:
        credential_status: The credentialStatus entry from the credential
        status_list_credential: The BitstringStatusListCredential
        
    Returns:
        tuple: (is_valid, reason_if_invalid)
        - is_valid: True if credential is NOT revoked/suspended
        - reason_if_invalid: None if valid, or explanation if invalid
    """
    # Validate credentialStatus structure
    if credential_status.get('type') != 'BitstringStatusListEntry':
        return False, f"Unsupported credentialStatus type: {credential_status.get('type')}"
    
    status_purpose = credential_status.get('statusPurpose')
    if status_purpose not in ('revocation', 'suspension'):
        return False, f"Invalid statusPurpose: {status_purpose}"
    
    status_list_index = credential_status.get('statusListIndex')
    if status_list_index is None:
        return False, "Missing statusListIndex"
    
    try:
        index = int(status_list_index)
    except (ValueError, TypeError):
        return False, f"Invalid statusListIndex: {status_list_index}"
    
    status_list_url = credential_status.get('statusListCredential')
    if not status_list_url:
        return False, "Missing statusListCredential URL"
    
    # Verify the status list credential matches
    if status_list_credential.get('id') != status_list_url:
        return False, "Status list credential ID does not match expected URL"
    
    # Extract and decode bitstring
    subject = status_list_credential.get('credentialSubject', {})
    encoded_list = subject.get('encodedList')
    if not encoded_list:
        return False, "Status list missing encodedList"
    
    try:
        bitstring = decode_bitstring(encoded_list)
    except ValueError as e:
        return False, f"Failed to decode status list: {e}"
    
    # Check if index is within range
    total_bits = len(bitstring) * 8
    if index < 0 or index >= total_bits:
        return False, f"statusListIndex {index} out of range (0-{total_bits-1})"
    
    # Check the bit
    is_set = get_bit(bitstring, index)
    
    if is_set:
        if status_purpose == 'revocation':
            return False, "Credential has been revoked"
        else:
            return False, "Credential is suspended"
    
    return True, None


# Convenience functions for status list operations

def flip_bits(bitstring: bytes, indices: List[int], value: bool) -> bytes:
    """
    Set multiple bits to the same value in one operation.
    
    Args:
        bitstring: Current bitstring
        indices: List of bit indices to set
        value: Value to set (True=1, False=0)
        
    Returns:
        bytes: New bitstring with bits set
    """
    result = bitstring
    for index in indices:
        result = set_bit(result, index, value)
    return result


def count_set_bits(bitstring: bytes) -> int:
    """
    Count the number of bits set to 1.
    
    Args:
        bitstring: Bitstring bytes
        
    Returns:
        int: Count of bits set to 1
    """
    count = 0
    for byte in bitstring:
        # Brian Kernighan's algorithm for counting bits
        while byte:
            byte &= byte - 1
            count += 1
    return count


def get_bitstring_stats(bitstring: bytes) -> Dict[str, Any]:
    """
    Get statistics about a bitstring.
    
    Args:
        bitstring: Bitstring bytes
        
    Returns:
        dict with total_bits, set_bits, unset_bits, utilization_percent
    """
    total_bits = len(bitstring) * 8
    set_bits = count_set_bits(bitstring)
    unset_bits = total_bits - set_bits
    utilization = (set_bits / total_bits) * 100 if total_bits > 0 else 0
    
    return {
        'total_bits': total_bits,
        'set_bits': set_bits,
        'unset_bits': unset_bits,
        'utilization_percent': round(utilization, 4)
    }
