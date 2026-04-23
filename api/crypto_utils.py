"""
Shared cryptographic utilities for Observer Protocol.

Provides canonicalization, Ed25519 signature verification, and signed-request
authentication used across VC verification, status list updates, and
authenticated API requests.

Canonicalization uses JCS-compatible encoding (JSON with sorted keys, compact
separators, UTF-8). The 'proof' key is always excluded from the canonical form.
This matches the existing vc_issuer and vc_verifier implementations exactly.

Signature suite: Ed25519Signature2020 throughout.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import base58
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
    Ed25519PrivateKey,
)
from cryptography.exceptions import InvalidSignature


# Maximum age for signed requests before they are rejected (replay protection)
SIGNED_REQUEST_MAX_AGE_SECONDS = 300  # 5 minutes


def canonical_bytes(doc: dict) -> bytes:
    """
    Produce the canonical byte representation of a document for signing or
    verification.

    The 'proof' key is excluded. Keys are sorted recursively by Python's
    json.dumps(sort_keys=True). No extra whitespace. UTF-8 encoded.

    This is the single canonical implementation. Both vc_issuer and vc_verifier
    should import this rather than maintaining their own copies.
    """
    doc_without_proof = {k: v for k, v in doc.items() if k != "proof"}
    return json.dumps(
        doc_without_proof, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def decode_proof_value(proof_value: str) -> bytes:
    """
    Decode an Ed25519Signature2020 proofValue.
    Expects multibase base58btc encoding (prefix 'z').
    """
    if not isinstance(proof_value, str) or not proof_value.startswith("z"):
        raise ValueError(
            f"proofValue must be multibase base58btc (prefix 'z'), got: {proof_value!r}"
        )
    return base58.b58decode(proof_value[1:])


def encode_proof_value(sig_bytes: bytes) -> str:
    """
    Encode signature bytes as multibase base58btc (prefix 'z').
    """
    return "z" + base58.b58encode(sig_bytes).decode("ascii")


def load_public_key_from_hex(public_key_hex: str) -> Ed25519PublicKey:
    """Load an Ed25519PublicKey from a 64-hex-char (32-byte) hex string."""
    try:
        key_bytes = bytes.fromhex(public_key_hex)
    except ValueError as exc:
        raise ValueError(f"public_key_hex is not valid hex: {exc}") from exc
    if len(key_bytes) != 32:
        raise ValueError(
            f"Ed25519 public key must be 32 bytes, got {len(key_bytes)}."
        )
    return Ed25519PublicKey.from_public_bytes(key_bytes)


def load_public_key_from_multibase(multibase: str) -> Ed25519PublicKey:
    """Load an Ed25519PublicKey from a base58btc multibase string (prefix 'z')."""
    if not isinstance(multibase, str) or not multibase.startswith("z"):
        raise ValueError(
            "publicKeyMultibase must use base58btc encoding (prefix 'z')"
        )
    key_bytes = base58.b58decode(multibase[1:])
    if len(key_bytes) != 32:
        raise ValueError(
            f"Ed25519 public key must be 32 bytes, got {len(key_bytes)}."
        )
    return Ed25519PublicKey.from_public_bytes(key_bytes)


def verify_ed25519_proof(
    document: dict,
    public_key: Ed25519PublicKey,
) -> tuple[bool, str]:
    """
    Verify an Ed25519Signature2020 proof on a document (VC, VP, or signed request).

    Args:
        document: The full document dict including its 'proof' field.
        public_key: The Ed25519 public key to verify against.

    Returns:
        (True, "ok") on success.
        (False, "<reason>") on any failure.
    """
    try:
        proof = document.get("proof")
        if not proof:
            return False, "Document is missing a proof"
        if proof.get("type") != "Ed25519Signature2020":
            return False, f"Unsupported proof type: {proof.get('type')!r}"
        proof_value = proof.get("proofValue")
        if not proof_value:
            return False, "proof.proofValue is missing"

        sig_bytes = decode_proof_value(proof_value)
        message = canonical_bytes(document)
        public_key.verify(sig_bytes, message)

        return True, "ok"

    except InvalidSignature:
        return False, "Ed25519 signature verification failed"
    except ValueError as exc:
        return False, f"Proof decoding error: {exc}"
    except Exception as exc:
        return False, f"Verification error: {exc}"


def sign_document(document: dict, private_key: Ed25519PrivateKey, verification_method: str) -> dict:
    """
    Sign a document with Ed25519Signature2020 and return the document with proof attached.

    Args:
        document: The document dict (must not already contain 'proof').
        private_key: The Ed25519 private key to sign with.
        verification_method: The DID verification method URI (e.g., "did:web:...#key-1").

    Returns:
        The document dict with 'proof' field added.
    """
    message = canonical_bytes(document)
    sig_bytes = private_key.sign(message)

    signed = dict(document)
    signed["proof"] = {
        "type": "Ed25519Signature2020",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verificationMethod": verification_method,
        "proofPurpose": "assertionMethod",
        "proofValue": encode_proof_value(sig_bytes),
    }
    return signed


def extract_signer_did(proof: dict) -> str:
    """
    Extract the signer's DID from a proof's verificationMethod field.

    verificationMethod is typically "did:web:example.com:agents:foo#key-1".
    The DID is everything before the '#' fragment.
    """
    vm = proof.get("verificationMethod")
    if not vm or not isinstance(vm, str):
        raise ValueError("proof.verificationMethod is missing or not a string")
    # DID is the part before the fragment identifier
    did = vm.split("#")[0]
    if not did.startswith("did:"):
        raise ValueError(f"verificationMethod does not contain a valid DID: {vm!r}")
    return did


def extract_key_id(proof: dict) -> Optional[str]:
    """
    Extract the full key ID (verificationMethod URI) from a proof block.
    Returns the full verificationMethod value, which can be used to look up
    the specific key in a DID document.
    """
    vm = proof.get("verificationMethod")
    if not vm or not isinstance(vm, str):
        return None
    return vm


def check_proof_freshness(proof: dict, max_age_seconds: int = SIGNED_REQUEST_MAX_AGE_SECONDS) -> tuple[bool, str]:
    """
    Check that a proof's 'created' timestamp is recent enough (replay protection).

    Args:
        proof: The proof block from a signed document/request.
        max_age_seconds: Maximum allowed age in seconds.

    Returns:
        (True, "ok") if fresh enough.
        (False, "<reason>") if too old or malformed.
    """
    created_str = proof.get("created")
    if not created_str:
        return False, "proof.created is missing"

    try:
        created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        return False, f"proof.created is not a valid ISO 8601 timestamp: {exc}"

    now = datetime.now(timezone.utc)
    age = now - created

    if age > timedelta(seconds=max_age_seconds):
        return False, f"Signed request too old: created {created_str}, age {age.total_seconds():.0f}s exceeds {max_age_seconds}s limit"

    if age < timedelta(seconds=-30):
        return False, f"Signed request timestamp is in the future: {created_str}"

    return True, "ok"


def verify_signed_request(
    request_body: dict,
    resolve_did_document_fn,
) -> tuple[bool, str, Optional[str]]:
    """
    Verify a signed API request body.

    The request body must contain a 'proof' block with:
      - type: "Ed25519Signature2020"
      - created: ISO 8601 timestamp (replay protection, max 5 minutes)
      - verificationMethod: DID URI with key fragment (e.g., "did:web:...#key-1")
      - proofPurpose: "authentication"
      - proofValue: multibase base58btc signature

    The signer's DID is extracted from verificationMethod. The DID is resolved
    via resolve_did_document_fn to obtain the public key. The signature is
    verified against the canonical form of the request body (proof excluded).

    Args:
        request_body: The full request body dict including 'proof'.
        resolve_did_document_fn: Callable(did_string) -> did_document dict.
            Raises ValueError or similar on resolution failure.

    Returns:
        (True, "ok", signer_did) on success.
        (False, "<reason>", None) on any failure.
    """
    proof = request_body.get("proof")
    if not proof or not isinstance(proof, dict):
        return False, "Request body missing 'proof' block", None

    # Check proof structure
    if proof.get("type") != "Ed25519Signature2020":
        return False, f"Unsupported proof type: {proof.get('type')!r}", None

    if proof.get("proofPurpose") != "authentication":
        return False, f"proofPurpose must be 'authentication' for signed requests, got: {proof.get('proofPurpose')!r}", None

    # Replay protection
    fresh_ok, fresh_reason = check_proof_freshness(proof)
    if not fresh_ok:
        return False, fresh_reason, None

    # Extract signer DID and key ID
    try:
        signer_did = extract_signer_did(proof)
    except ValueError as exc:
        return False, str(exc), None

    key_id = extract_key_id(proof)

    # Resolve DID document
    try:
        did_document = resolve_did_document_fn(signer_did)
    except Exception as exc:
        return False, f"Failed to resolve signer DID {signer_did}: {exc}", None

    # Extract public key from DID document
    methods = did_document.get("verificationMethod", [])
    if not methods:
        return False, f"No verificationMethod in DID document for {signer_did}", None

    # Match by key_id if provided
    vm = None
    if key_id:
        vm = next((m for m in methods if m.get("id") == key_id), None)
    if vm is None:
        vm = methods[0]

    multibase = vm.get("publicKeyMultibase", "")
    try:
        public_key = load_public_key_from_multibase(multibase)
    except ValueError as exc:
        return False, f"Cannot load public key from DID document: {exc}", None

    # Verify signature
    ok, reason = verify_ed25519_proof(request_body, public_key)
    if not ok:
        return False, reason, None

    return True, "ok", signer_did
