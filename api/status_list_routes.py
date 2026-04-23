"""
Spec 3.3 — Status List API endpoints.

Five endpoints per the spec:

  GET  /sovereign/status-lists/<list-id>              — retrieve status list (public)
  POST /sovereign/status-lists                        — allocate new list (signed request)
  POST /sovereign/status-lists/<list-id>/allocate-index — reserve next index (signed request)
  POST /sovereign/status-lists/<list-id>              — update status list (VC-signature auth)
  POST /verify/status                                 — convenience status check (public)

Auth model:
  - GET and /verify/status are unauthenticated.
  - Allocate endpoints use signed-request-body auth: the request body contains a
    proof block with proofPurpose "authentication", signed by the requester's DID.
    The signer DID is extracted from proof.verificationMethod.
  - Update endpoint uses VC-signature auth: the submitted BitstringStatusListCredential
    is itself the auth token. The signer DID is extracted from the credential's proof
    block and checked against the revocation authority model.

Request signing pattern (for client implementers):
  1. Construct the request body as JSON (without the proof field).
  2. Canonicalize: JSON.stringify with sorted keys, compact separators, UTF-8.
  3. Sign the canonical bytes with your Ed25519 private key.
  4. Add a proof block:
       {
         "type": "Ed25519Signature2020",
         "created": "<ISO 8601 UTC timestamp>",
         "verificationMethod": "<your-did>#<key-id>",
         "proofPurpose": "authentication",
         "proofValue": "z<base58btc-encoded-signature>"
       }
  5. Submit the full body (original fields + proof) as JSON.
  The proof.created timestamp must be within 5 minutes of server time (replay protection).
  The DID in verificationMethod must be resolvable and contain the signing key.
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from crypto_utils import (
    verify_signed_request,
    verify_ed25519_proof,
    extract_signer_did,
    load_public_key_from_multibase,
)
from bitstring_status_list import (
    decode_bitstring,
    validate_status_list_update,
)
from status_list_store import (
    create_status_list,
    get_status_list,
    get_status_list_credential,
    allocate_index,
    update_status_list,
    StatusListNotFoundError,
    StatusListCapacityExhaustedError,
    StatusListOwnerMismatchError,
)
from status_checker import check_credential_status


router = APIRouter()


# ---------------------------------------------------------------------------
# Dependencies injected by the application at startup
# ---------------------------------------------------------------------------

# These are set by the application (or test fixtures) before the router is used.
# Using module-level callables avoids coupling to a specific DI framework.

_get_db_connection = None   # Callable() -> psycopg2 connection
_resolve_did = None         # Callable(did_string) -> did_document dict
_base_url = None            # str, e.g. "https://api.observerprotocol.org"


def configure(
    get_db_connection_fn,
    resolve_did_fn,
    base_url: str,
):
    """
    Configure the router's dependencies. Must be called before handling requests.
    """
    global _get_db_connection, _resolve_did, _base_url
    _get_db_connection = get_db_connection_fn
    _resolve_did = resolve_did_fn
    _base_url = base_url


def _require_configured():
    if _get_db_connection is None or _resolve_did is None or _base_url is None:
        raise RuntimeError(
            "status_lists router not configured. Call configure() at startup."
        )


# ---------------------------------------------------------------------------
# GET /sovereign/status-lists/{list_id} — Retrieve status list (public)
# ---------------------------------------------------------------------------

@router.get("/sovereign/status-lists/{list_id}")
def get_status_list_endpoint(list_id: str):
    """
    Serve the current BitstringStatusListCredential for a status list.

    Unauthenticated. This is the URL that verifiers hit when checking
    credentialStatus.statusListCredential.
    """
    _require_configured()
    conn = _get_db_connection()
    try:
        cred = get_status_list_credential(conn, list_id)
        if cred is None:
            raise HTTPException(status_code=404, detail=f"Status list {list_id!r} not found")
        return JSONResponse(content=cred)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /sovereign/status-lists — Allocate new status list (signed request)
# ---------------------------------------------------------------------------

@router.post("/sovereign/status-lists", status_code=201)
async def allocate_status_list_endpoint(request: Request):
    """
    Allocate a new status list for an issuer.

    Request body (signed):
        {
          "statusPurpose": "revocation" | "suspension",
          "proof": { ... Ed25519Signature2020, proofPurpose: "authentication" ... }
        }

    The signer DID (extracted from proof.verificationMethod) becomes the list owner.
    """
    _require_configured()

    body = await request.json()

    # Validate required fields (before auth, so we give useful errors)
    status_purpose = body.get("statusPurpose")
    if status_purpose not in ("revocation", "suspension"):
        raise HTTPException(
            status_code=400,
            detail="statusPurpose must be 'revocation' or 'suspension'",
        )

    # Verify signed request
    ok, reason, signer_did = verify_signed_request(body, _resolve_did)
    if not ok:
        raise HTTPException(status_code=403, detail=f"Authentication failed: {reason}")

    # Create the status list
    conn = _get_db_connection()
    try:
        result = create_status_list(
            conn=conn,
            owner_did=signer_did,
            status_purpose=status_purpose,
            base_url=_base_url,
        )
        return JSONResponse(content=result, status_code=201)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /sovereign/status-lists/{list_id}/allocate-index — Reserve next index
# ---------------------------------------------------------------------------

@router.post("/sovereign/status-lists/{list_id}/allocate-index")
async def allocate_index_endpoint(list_id: str, request: Request):
    """
    Atomically allocate the next available index on a status list.

    Request body (signed):
        {
          "proof": { ... Ed25519Signature2020, proofPurpose: "authentication" ... }
        }

    The signer DID must match the list's owner DID.
    """
    _require_configured()

    body = await request.json()

    # Verify signed request
    ok, reason, signer_did = verify_signed_request(body, _resolve_did)
    if not ok:
        raise HTTPException(status_code=403, detail=f"Authentication failed: {reason}")

    conn = _get_db_connection()
    try:
        result = allocate_index(conn, list_id, signer_did)
        return JSONResponse(content=result)
    except StatusListNotFoundError:
        raise HTTPException(status_code=404, detail=f"Status list {list_id!r} not found")
    except StatusListOwnerMismatchError:
        raise HTTPException(
            status_code=403,
            detail=f"DID {signer_did!r} is not the owner of status list {list_id!r}",
        )
    except StatusListCapacityExhaustedError:
        raise HTTPException(
            status_code=409,
            detail=f"Status list {list_id!r} is full. Allocate a new list.",
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /sovereign/status-lists/{list_id} — Update status list (VC-signature)
# ---------------------------------------------------------------------------

@router.post("/sovereign/status-lists/{list_id}")
async def update_status_list_endpoint(list_id: str, request: Request):
    """
    Submit an updated signed BitstringStatusListCredential.

    Request body:
        {
          "credential": { ... full signed BitstringStatusListCredential ... }
        }

    Auth: the credential's proof signature is verified against the signer's
    DID document. The signer must have revocation authority over every
    credential whose bit changed from 0 to 1.

    Validation:
      1. Valid BSL v1.0 structure.
      2. Signature valid for signing DID.
      3. Signing DID matches the list's owner (for attestation revocations).
         For delegation revocations, authority is checked against the chain
         (§6.3 of the spec — implemented when Spec 3.2 integration lands).
      4. No 1→0 flips for statusPurpose "revocation" (revocation is terminal).
    """
    _require_configured()

    body = await request.json()

    credential = body.get("credential")
    if not credential or not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="Request body must contain a 'credential' field")

    # Structural validation: must be a BitstringStatusListCredential
    cred_types = credential.get("type", [])
    if "BitstringStatusListCredential" not in cred_types:
        raise HTTPException(
            status_code=400,
            detail="credential.type must include 'BitstringStatusListCredential'",
        )

    subject = credential.get("credentialSubject", {})
    if subject.get("type") != "BitstringStatusList":
        raise HTTPException(
            status_code=400,
            detail="credentialSubject.type must be 'BitstringStatusList'",
        )

    new_encoded = subject.get("encodedList")
    if not new_encoded:
        raise HTTPException(status_code=400, detail="credentialSubject.encodedList is required")

    new_purpose = subject.get("statusPurpose")
    if not new_purpose:
        raise HTTPException(status_code=400, detail="credentialSubject.statusPurpose is required")

    # Verify the credential's signature
    proof = credential.get("proof")
    if not proof:
        raise HTTPException(status_code=400, detail="Credential is missing a proof")

    try:
        signer_did = extract_signer_did(proof)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        did_doc = _resolve_did(signer_did)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot resolve signer DID: {exc}")

    # Extract public key and verify signature
    key_id = proof.get("verificationMethod")
    methods = did_doc.get("verificationMethod", [])
    vm = None
    if key_id:
        vm = next((m for m in methods if m.get("id") == key_id), None)
    if vm is None and methods:
        vm = methods[0]
    if vm is None:
        raise HTTPException(status_code=400, detail="No verificationMethod in signer's DID document")

    try:
        pub_key = load_public_key_from_multibase(vm.get("publicKeyMultibase", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Cannot load public key: {exc}")

    sig_ok, sig_err = verify_ed25519_proof(credential, pub_key)
    if not sig_ok:
        raise HTTPException(status_code=403, detail=f"Credential signature verification failed: {sig_err}")

    # Fetch current state and validate the update
    conn = _get_db_connection()
    try:
        current = get_status_list(conn, list_id)
        if current is None:
            raise HTTPException(status_code=404, detail=f"Status list {list_id!r} not found")

        # Purpose must match
        if new_purpose != current["status_purpose"]:
            raise HTTPException(
                status_code=400,
                detail=f"statusPurpose mismatch: list is '{current['status_purpose']}', credential says '{new_purpose}'",
            )

        # Authority check: signer must be the list owner (attestation model).
        # For delegation chain authority (§6.3), this check will be extended
        # when Spec 3.2 integration lands. For now, owner-only.
        if signer_did != current["owner_did"]:
            raise HTTPException(
                status_code=403,
                detail=f"DID {signer_did!r} is not authorized to update status list {list_id!r}",
            )

        # Validate bitstring changes
        valid, reason, changes = validate_status_list_update(
            current["current_bitstring"],
            new_encoded,
            current["status_purpose"],
        )
        if not valid:
            raise HTTPException(status_code=400, detail=f"Invalid status list update: {reason}")

        # Apply the update
        result = update_status_list(conn, list_id, credential, new_encoded)
        result["bitsChanged"] = len(changes)
        return JSONResponse(content=result)

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /verify/status — Convenience status check (public)
# ---------------------------------------------------------------------------

@router.post("/verify/status")
async def verify_status_endpoint(request: Request):
    """
    Check the revocation/suspension status of a credential.

    Request body:
        {
          "credential": { ... full credential VC including credentialStatus ... }
        }

    Unauthenticated. Fetches the referenced status list(s), decodes the
    bitstring, and checks the bit at the credential's index.

    Note: this is a convenience endpoint. High-stakes verification should be
    performed by the counterparty directly to avoid the network dependency
    (Build Principles §2.4).
    """
    _require_configured()

    body = await request.json()
    credential = body.get("credential")
    if not credential or not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="Request body must contain a 'credential' field")

    def fetch_status_list(url: str):
        """Fetch a status list credential by URL. Handles both OP-hosted and external."""
        # Check if it's an OP-hosted list (URL matches our base)
        prefix = f"{_base_url}/sovereign/status-lists/"
        if url.startswith(prefix):
            list_id = url[len(prefix):]
            conn = _get_db_connection()
            try:
                return get_status_list_credential(conn, list_id)
            finally:
                conn.close()
        # External list: would need HTTP fetch. For now, return None.
        # Full external fetch support is added when Tier 2 verification lands.
        return None

    result = check_credential_status(
        credential,
        fetch_status_list_fn=fetch_status_list,
        resolve_did_fn=_resolve_did,
    )
    return JSONResponse(content=result)
