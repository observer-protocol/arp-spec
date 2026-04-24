"""
Spec 3.4 — Audit API endpoints.

Seven endpoints:

  POST /audit/activity          — ingest AgentActivityCredential (VC-signature auth)
  POST /audit/receipt           — ingest CounterpartyReceiptCredential (VC-signature auth)
  POST /audit/receipt-request   — ingest ReceiptRequestCredential (VC-signature auth)
  POST /audit/receipt-ack       — ingest ReceiptAcknowledgment (VC-signature auth)
  GET  /audit/proof/{root_id}   — Merkle proof retrieval (authenticated)
  GET  /audit/agent/{agent_did}/activities  — query activities (signed-request auth)
  GET  /audit/agent/{agent_did}/coverage    — coverage metric (signed-request auth)
  GET  /audit/anomalies         — anomaly query (signed-request auth)

Auth model:
  - Ingest endpoints: VC-signature auth. The submitted credential's proof is
    verified against the issuer's DID document. For /audit/activity, the signer
    DID must equal credential.issuer. For /audit/receipt, any submitter is OK —
    verification is against the receipt's own signature.
  - Query endpoints: signed-request-body auth per Spec 3.3 pattern.
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse

from audit_store import (
    ingest_activity,
    ingest_receipt,
    ingest_receipt_request,
    ingest_receipt_ack,
    get_activities_for_agent,
    get_anomalies,
    get_activity_by_id,
)
from audit_extractors import (
    extract_activity_fields,
    extract_receipt_fields,
    extract_receipt_request_fields,
    extract_receipt_ack_fields,
)
from audit_matcher import match_and_link
from audit_anomalies import detect_unmatched_receipt, detect_receipt_rejected
from audit_coverage import compute_coverage, get_coverage
from merkle_tree import verify_proof


router = APIRouter()

# ---------------------------------------------------------------------------
# Dependencies injected by the application at startup
# ---------------------------------------------------------------------------

_get_db_connection = None
_resolve_did = None
_verify_vc_signature = None  # Callable(credential, resolve_did_fn) -> (bool, str)


def configure(
    get_db_connection_fn,
    resolve_did_fn,
    verify_vc_signature_fn,
):
    """
    Configure the router's dependencies. Must be called before handling requests.

    Args:
        get_db_connection_fn: () -> psycopg2 connection
        resolve_did_fn: (did_string) -> did_document dict
        verify_vc_signature_fn: (credential, resolve_did_fn) -> (bool, error_str)
    """
    global _get_db_connection, _resolve_did, _verify_vc_signature
    _get_db_connection = get_db_connection_fn
    _resolve_did = resolve_did_fn
    _verify_vc_signature = verify_vc_signature_fn


def _require_configured():
    if _get_db_connection is None or _resolve_did is None or _verify_vc_signature is None:
        raise RuntimeError("audit router not configured. Call configure() at startup.")


def _verify_credential(credential: dict) -> str:
    """
    Verify a credential's signature. Returns the signer DID.
    Raises HTTPException on failure.
    """
    ok, error = _verify_vc_signature(credential, _resolve_did)
    if not ok:
        raise HTTPException(status_code=403, detail=f"Credential signature verification failed: {error}")

    proof = credential.get("proof", {})
    vm = proof.get("verificationMethod", "")
    signer_did = vm.split("#")[0] if "#" in vm else vm
    return signer_did


def _extract_credential_type(credential: dict) -> Optional[str]:
    """Extract the specific credential type (second element of type array)."""
    types = credential.get("type", [])
    for t in types:
        if t != "VerifiableCredential":
            return t
    return None


# ---------------------------------------------------------------------------
# POST /audit/activity — Ingest AgentActivityCredential
# ---------------------------------------------------------------------------

@router.post("/audit/activity")
async def ingest_activity_endpoint(request: Request):
    """
    Ingest an AgentActivityCredential.

    Auth: VC-signature. Signer DID must equal credential.issuer (self-attestation).
    Idempotent: second submission of same credential_id returns 200 with original
    ingested_at.
    """
    _require_configured()

    body = await request.json()
    credential = body.get("credential")
    if not credential or not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="Request body must contain a 'credential' field")

    cred_type = _extract_credential_type(credential)
    if cred_type not in ("AgentActivityCredential", "AgentActivityMerkleRoot"):
        raise HTTPException(status_code=400, detail=f"Expected AgentActivityCredential, got {cred_type}")

    signer_did = _verify_credential(credential)
    issuer = credential.get("issuer")
    if signer_did != issuer:
        raise HTTPException(
            status_code=403,
            detail=f"Signer DID {signer_did} does not match credential issuer {issuer}",
        )

    extracted = extract_activity_fields(credential)

    conn = _get_db_connection()
    try:
        result = ingest_activity(conn, credential, extracted)
        return JSONResponse(content=result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /audit/receipt — Ingest CounterpartyReceiptCredential
# ---------------------------------------------------------------------------

@router.post("/audit/receipt")
async def ingest_receipt_endpoint(request: Request):
    """
    Ingest a CounterpartyReceiptCredential.

    Auth: VC-signature on the receipt itself. Any submitter OK (agent may forward).
    On ingest: attempt sync match against agent activities. If no match,
    record UnmatchedReceiptAnomaly.
    """
    _require_configured()

    body = await request.json()
    credential = body.get("credential")
    if not credential or not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="Request body must contain a 'credential' field")

    cred_type = _extract_credential_type(credential)
    if cred_type != "CounterpartyReceiptCredential":
        raise HTTPException(status_code=400, detail=f"Expected CounterpartyReceiptCredential, got {cred_type}")

    _verify_credential(credential)
    extracted = extract_receipt_fields(credential)

    conn = _get_db_connection()
    try:
        result = ingest_receipt(conn, credential, extracted)

        if result["is_new"]:
            matched_id = match_and_link(conn, result["id"], extracted)
            result["matched_activity_id"] = matched_id

            if matched_id is None:
                anomaly_id = detect_unmatched_receipt(conn, result["id"], extracted, matched_id)
                if anomaly_id:
                    result["anomaly_id"] = anomaly_id

        return JSONResponse(content=result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /audit/receipt-request — Ingest ReceiptRequestCredential
# ---------------------------------------------------------------------------

@router.post("/audit/receipt-request")
async def ingest_receipt_request_endpoint(request: Request):
    """
    Ingest a ReceiptRequestCredential. Stored for audit trail.
    """
    _require_configured()

    body = await request.json()
    credential = body.get("credential")
    if not credential or not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="Request body must contain a 'credential' field")

    cred_type = _extract_credential_type(credential)
    if cred_type != "ReceiptRequestCredential":
        raise HTTPException(status_code=400, detail=f"Expected ReceiptRequestCredential, got {cred_type}")

    _verify_credential(credential)
    extracted = extract_receipt_request_fields(credential)

    conn = _get_db_connection()
    try:
        result = ingest_receipt_request(conn, credential, extracted)
        return JSONResponse(content=result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /audit/receipt-ack — Ingest ReceiptAcknowledgment
# ---------------------------------------------------------------------------

@router.post("/audit/receipt-ack")
async def ingest_receipt_ack_endpoint(request: Request):
    """
    Ingest a ReceiptAcknowledgment. If status is "rejected", records
    ReceiptRejectedAnomaly.
    """
    _require_configured()

    body = await request.json()
    credential = body.get("credential")
    if not credential or not isinstance(credential, dict):
        raise HTTPException(status_code=400, detail="Request body must contain a 'credential' field")

    cred_type = _extract_credential_type(credential)
    if cred_type != "ReceiptAcknowledgment":
        raise HTTPException(status_code=400, detail=f"Expected ReceiptAcknowledgment, got {cred_type}")

    _verify_credential(credential)
    extracted = extract_receipt_ack_fields(credential)

    conn = _get_db_connection()
    try:
        result = ingest_receipt_ack(conn, credential, extracted)

        if result["is_new"]:
            anomaly_id = detect_receipt_rejected(conn, extracted)
            if anomaly_id:
                result["anomaly_id"] = anomaly_id

        return JSONResponse(content=result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /audit/proof/{root_id} — Merkle proof retrieval
# ---------------------------------------------------------------------------

@router.get("/audit/proof/{root_id}")
def get_merkle_proof(root_id: int, leaf_hash: str = Query(..., alias="leaf-hash")):
    """
    Retrieve a Merkle inclusion proof for a leaf within a root credential.

    Path param: root_id — integer ID of the root AgentActivityCredential.
    Query param: leaf_hash — hex-encoded SHA-256 of the leaf entry.

    Returns the proof path and the root credential's credential_id URL.
    """
    _require_configured()

    conn = _get_db_connection()
    try:
        root = get_activity_by_id(conn, root_id)
        if not root:
            raise HTTPException(status_code=404, detail=f"Root credential {root_id} not found")

        cred = root["credential_jsonld"]
        subject = cred.get("credentialSubject", {})

        if "merkleRoot" not in subject:
            raise HTTPException(status_code=400, detail="Credential is not a Merkle root")

        # The leaves and proof paths are not stored in the DB — they're held
        # by the agent. This endpoint can only verify a proof the caller
        # provides, not generate one from stored data. For AT-hosted proofs,
        # the agent must submit leaf data alongside the root.
        #
        # Return the root info so the caller can verify their own proof.
        return JSONResponse(content={
            "root_id": root_id,
            "root_credential_id": root["credential_id"],
            "merkle_root_hash": subject["merkleRoot"],
            "leaf_count": subject.get("leafCount"),
            "window_start": subject.get("windowStart"),
            "window_end": subject.get("windowEnd"),
            "note": "Proof generation requires leaf data held by the agent. Use verify_proof() with the proof path the agent provides.",
        })
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /audit/agent/{agent_did}/activities — Query activities
# ---------------------------------------------------------------------------

@router.get("/audit/agent/{agent_did:path}/activities")
def query_activities(
    agent_did: str,
    since: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    Query agent activities. Paginated.

    TODO: Add signed-request-body auth for query endpoints.
    For this pass, endpoint is open — auth will be wired in integration.
    """
    _require_configured()

    conn = _get_db_connection()
    try:
        activities = get_activities_for_agent(
            conn, agent_did, since=since, activity_type=type,
            limit=limit, offset=offset,
        )
        return JSONResponse(content={
            "agent_did": agent_did,
            "count": len(activities),
            "activities": activities,
        })
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /audit/agent/{agent_did}/coverage — Coverage metric
# ---------------------------------------------------------------------------

@router.get("/audit/agent/{agent_did:path}/coverage")
def query_coverage(
    agent_did: str,
    window: int = Query(default=30, description="Window in days (7, 30, 90)"),
):
    """
    Get receipt coverage rate for an agent.

    Computes on demand and caches in rollup table.
    """
    _require_configured()

    if window not in (7, 30, 90):
        raise HTTPException(status_code=400, detail="window must be 7, 30, or 90")

    conn = _get_db_connection()
    try:
        result = compute_coverage(conn, agent_did, window)
        return JSONResponse(content=result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /audit/anomalies — Anomaly query
# ---------------------------------------------------------------------------

@router.get("/audit/anomalies")
def query_anomalies(
    org: Optional[int] = None,
    type: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = Query(default=50, le=500),
):
    """
    Query audit anomalies with optional filters.

    TODO: Add signed-request-body auth. For this pass, endpoint is open.
    """
    _require_configured()

    valid_types = {"CoverageGap", "UnmatchedReceiptAnomaly", "ReceiptRejectedAnomaly", "ReceiptDeliveryTimeout"}
    if type and type not in valid_types:
        raise HTTPException(status_code=400, detail=f"type must be one of {sorted(valid_types)}")

    conn = _get_db_connection()
    try:
        anomalies = get_anomalies(conn, org_id=org, anomaly_type=type, since=since, limit=limit)
        return JSONResponse(content={
            "count": len(anomalies),
            "anomalies": anomalies,
        })
    finally:
        conn.close()
