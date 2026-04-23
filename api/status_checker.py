"""
Credential status checker — given a credential with credentialStatus,
fetch the referenced status list(s), decode the bitstring, and check the bit.

This module is used by:
  - POST /verify/status endpoint (check status of an arbitrary credential)
  - AT cache invalidation logic (re-check status on cached credentials)

It does NOT verify the credential's own signature — only its revocation/suspension
status. Signature verification is a separate step performed by the caller.
"""

from typing import Optional, Callable

from bitstring_status_list import decode_bitstring, get_bit
from crypto_utils import (
    verify_ed25519_proof,
    load_public_key_from_multibase,
    extract_signer_did,
)


class StatusCheckResult:
    """Result of checking a single credentialStatus entry."""

    def __init__(
        self,
        status_purpose: str,
        status_list_url: str,
        status_list_index: int,
        current_value: int,
        valid_for_purpose: bool,
        error: Optional[str] = None,
    ):
        self.status_purpose = status_purpose
        self.status_list_url = status_list_url
        self.status_list_index = status_list_index
        self.current_value = current_value
        self.valid_for_purpose = valid_for_purpose
        self.error = error

    def to_dict(self) -> dict:
        d = {
            "status_purpose": self.status_purpose,
            "status_list_url": self.status_list_url,
            "status_list_index": self.status_list_index,
            "current_value": self.current_value,
            "valid_for_purpose": self.valid_for_purpose,
        }
        if self.error:
            d["error"] = self.error
        return d


def check_credential_status(
    credential: dict,
    fetch_status_list_fn: Callable[[str], Optional[dict]],
    resolve_did_fn: Optional[Callable[[str], dict]] = None,
) -> dict:
    """
    Check the revocation/suspension status of a credential.

    Reads the credential's credentialStatus field (array of
    BitstringStatusListEntry), fetches each referenced status list,
    verifies the status list signature (if resolve_did_fn provided),
    decodes the bitstring, and checks the bit at the credential's index.

    Args:
        credential: The full credential VC dict (must have credentialStatus).
        fetch_status_list_fn: Callable(url) -> BitstringStatusListCredential dict
            or None. For OP-hosted lists, this reads from the DB. For external
            lists, this fetches via HTTP.
        resolve_did_fn: Optional callable(did) -> DID document dict. If provided,
            the status list credential's signature is verified against the
            issuer's DID document. If None, signature verification is skipped
            (caller is responsible).

    Returns:
        Dict with:
            credential_id: str
            status_checks: list of StatusCheckResult dicts
            overall_valid: bool (True if no status flag is set)
    """
    credential_id = credential.get("id", "unknown")
    status_entries = credential.get("credentialStatus")

    if not status_entries:
        return {
            "credential_id": credential_id,
            "status_checks": [],
            "overall_valid": True,
        }

    # Normalize to list (spec says array, but handle single entry gracefully)
    if isinstance(status_entries, dict):
        status_entries = [status_entries]

    results = []
    overall_valid = True

    for entry in status_entries:
        result = _check_single_entry(entry, fetch_status_list_fn, resolve_did_fn)
        results.append(result)
        if not result.valid_for_purpose:
            overall_valid = False

    return {
        "credential_id": credential_id,
        "status_checks": [r.to_dict() for r in results],
        "overall_valid": overall_valid,
    }


def _check_single_entry(
    entry: dict,
    fetch_status_list_fn: Callable[[str], Optional[dict]],
    resolve_did_fn: Optional[Callable[[str], dict]],
) -> StatusCheckResult:
    """Check a single credentialStatus entry."""

    entry_type = entry.get("type")
    if entry_type != "BitstringStatusListEntry":
        return StatusCheckResult(
            status_purpose=entry.get("statusPurpose", "unknown"),
            status_list_url=entry.get("statusListCredential", "unknown"),
            status_list_index=-1,
            current_value=-1,
            valid_for_purpose=False,
            error=f"Unsupported credentialStatus type: {entry_type!r}",
        )

    status_purpose = entry.get("statusPurpose", "")
    status_list_url = entry.get("statusListCredential", "")
    try:
        status_list_index = int(entry.get("statusListIndex", -1))
    except (TypeError, ValueError):
        return StatusCheckResult(
            status_purpose=status_purpose,
            status_list_url=status_list_url,
            status_list_index=-1,
            current_value=-1,
            valid_for_purpose=False,
            error="statusListIndex is not a valid integer",
        )

    if not status_list_url:
        return StatusCheckResult(
            status_purpose=status_purpose,
            status_list_url="",
            status_list_index=status_list_index,
            current_value=-1,
            valid_for_purpose=False,
            error="statusListCredential URL is missing",
        )

    # Fetch the status list credential
    status_list_cred = fetch_status_list_fn(status_list_url)
    if status_list_cred is None:
        return StatusCheckResult(
            status_purpose=status_purpose,
            status_list_url=status_list_url,
            status_list_index=status_list_index,
            current_value=-1,
            valid_for_purpose=False,
            error=f"Status list not found at {status_list_url}",
        )

    # Optionally verify the status list credential's signature
    if resolve_did_fn is not None:
        sig_ok, sig_err = _verify_status_list_signature(status_list_cred, resolve_did_fn)
        if not sig_ok:
            return StatusCheckResult(
                status_purpose=status_purpose,
                status_list_url=status_list_url,
                status_list_index=status_list_index,
                current_value=-1,
                valid_for_purpose=False,
                error=f"Status list signature verification failed: {sig_err}",
            )

    # Extract and decode the bitstring
    subject = status_list_cred.get("credentialSubject", {})
    encoded_list = subject.get("encodedList")
    if not encoded_list:
        return StatusCheckResult(
            status_purpose=status_purpose,
            status_list_url=status_list_url,
            status_list_index=status_list_index,
            current_value=-1,
            valid_for_purpose=False,
            error="Status list credential missing encodedList",
        )

    try:
        raw = decode_bitstring(encoded_list)
    except ValueError as exc:
        return StatusCheckResult(
            status_purpose=status_purpose,
            status_list_url=status_list_url,
            status_list_index=status_list_index,
            current_value=-1,
            valid_for_purpose=False,
            error=f"Bitstring decode failed: {exc}",
        )

    # Check the bit
    try:
        bit_value = get_bit(raw, status_list_index)
    except IndexError as exc:
        return StatusCheckResult(
            status_purpose=status_purpose,
            status_list_url=status_list_url,
            status_list_index=status_list_index,
            current_value=-1,
            valid_for_purpose=False,
            error=f"Index out of range: {exc}",
        )

    # bit 0 = valid, bit 1 = actioned (revoked or suspended)
    valid_for_purpose = bit_value == 0

    return StatusCheckResult(
        status_purpose=status_purpose,
        status_list_url=status_list_url,
        status_list_index=status_list_index,
        current_value=bit_value,
        valid_for_purpose=valid_for_purpose,
    )


def _verify_status_list_signature(
    status_list_cred: dict,
    resolve_did_fn: Callable[[str], dict],
) -> tuple[bool, str]:
    """Verify the signature on a BitstringStatusListCredential."""
    proof = status_list_cred.get("proof")
    if not proof:
        return False, "Status list credential has no proof"

    try:
        issuer_did = extract_signer_did(proof)
    except ValueError as exc:
        return False, str(exc)

    try:
        did_doc = resolve_did_fn(issuer_did)
    except Exception as exc:
        return False, f"Cannot resolve status list issuer DID: {exc}"

    # Extract public key
    key_id = proof.get("verificationMethod")
    methods = did_doc.get("verificationMethod", [])
    vm = None
    if key_id:
        vm = next((m for m in methods if m.get("id") == key_id), None)
    if vm is None and methods:
        vm = methods[0]
    if vm is None:
        return False, "No verificationMethod in issuer DID document"

    multibase = vm.get("publicKeyMultibase", "")
    try:
        pub_key = load_public_key_from_multibase(multibase)
    except ValueError as exc:
        return False, f"Cannot load public key: {exc}"

    return verify_ed25519_proof(status_list_cred, pub_key)
