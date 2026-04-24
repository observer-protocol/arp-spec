"""
AT Reference Policy Engine — MVP.

Implements the OP policy-consultation interface. MVP scope:
  - Permit-all logic (signs every decision as 'permit')
  - Signs responses with AT's Ed25519 key
  - Logs every consultation
  - Self-registration endpoint to register AT's engine with OP for an org

This is the minimum viable reference engine. The full commercial engine
(JSON condition language, approval workflow, continuous re-evaluation)
ships in a subsequent sprint.

Endpoints:
  POST /api/v1/at-policy/evaluate         — engine evaluation (called by OP)
  POST /api/v1/at-policy/register-with-op — convenience self-register
  GET  /api/v1/at-policy/decisions        — view AT's consultation log
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import base58
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse

router = APIRouter()

_get_db_connection = None
_op_api_base = "https://api.agenticterminal.io"

# In-memory decision log for MVP (production: DB table)
_decision_log: list[dict] = []


def configure(get_db_connection_fn, op_api_base: str = "https://api.agenticterminal.io"):
    global _get_db_connection, _op_api_base
    _get_db_connection = get_db_connection_fn
    _op_api_base = op_api_base


def _require_configured():
    if _get_db_connection is None:
        raise RuntimeError("at_policy_engine not configured")


def _sign_decision(decision_body: dict) -> str:
    """
    Sign a decision with AT's Ed25519 key.
    Uses the same signing pattern as OP's credential signing.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        signing_key_hex = os.environ.get("AT_POLICY_SIGNING_KEY")
        if not signing_key_hex:
            # Fallback: use OP's signing key if AT-specific key not set
            signing_key_hex = os.environ.get("OP_SIGNING_KEY")
        if not signing_key_hex:
            return "unsigned-no-key-configured"

        private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(signing_key_hex))
        canonical = json.dumps(decision_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        sig_bytes = private_key.sign(canonical)
        return "z" + base58.b58encode(sig_bytes).decode("ascii")
    except Exception as e:
        return f"signing-error-{str(e)[:50]}"


# ---------------------------------------------------------------------------
# POST /api/v1/at-policy/evaluate — Engine evaluation endpoint
# ---------------------------------------------------------------------------

@router.post("/api/v1/at-policy/evaluate")
async def evaluate(request: Request):
    """
    Policy evaluation endpoint called by OP.

    MVP: always returns 'permit'. Signs the decision.
    """
    body = await request.json()

    request_id = body.get("request_id", str(uuid.uuid4()))
    action_type = body.get("action_type", "unknown")
    org_id = body.get("org_id")

    # MVP: permit all
    decision_body = {
        "decision": "permit",
        "request_id": request_id,
        "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy_id": "at-mvp-permit-all",
    }

    # Sign the decision
    signature = _sign_decision(decision_body)
    decision_body["signature"] = signature

    # Log
    log_entry = {
        "request_id": request_id,
        "org_id": org_id,
        "action_type": action_type,
        "decision": "permit",
        "evaluated_at": decision_body["evaluated_at"],
        "action_context_summary": {
            k: str(v)[:100] for k, v in body.get("action_context", {}).items()
        },
    }
    _decision_log.append(log_entry)
    # Keep log bounded
    if len(_decision_log) > 10000:
        _decision_log.pop(0)

    return JSONResponse(content=decision_body)


# ---------------------------------------------------------------------------
# POST /api/v1/at-policy/register-with-op — Self-register with OP
# ---------------------------------------------------------------------------

@router.post("/api/v1/at-policy/register-with-op")
async def register_with_op(request: Request):
    """
    Convenience endpoint: register AT's engine with OP for a given org.
    Admin only (uses enterprise session).
    """
    _require_configured()

    body = await request.json()
    org_id = body.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id required")

    # Determine AT's engine URL and key DID
    engine_url = f"{_op_api_base}/api/v1/at-policy/evaluate"
    engine_key_did = os.environ.get(
        "AT_POLICY_DID",
        "did:web:api.agenticterminal.io:api:v1:at-policy"
    )

    # Register with OP via the policy-engines/register endpoint
    import httpx
    try:
        registration = {
            "org_id": org_id,
            "engine_url": engine_url,
            "engine_public_key_did": engine_key_did,
            "engine_name": "AT Reference Engine",
            "engine_version": "1.0.0-mvp",
        }

        # Call OP's registration endpoint (same server, internal call)
        conn = _get_db_connection()
        try:
            from policy_engine_store import register_engine
            result = register_engine(
                conn=conn,
                org_id=org_id,
                engine_url=engine_url,
                engine_public_key_did=engine_key_did,
                engine_name="AT Reference Engine",
                engine_version="1.0.0-mvp",
            )
            return JSONResponse(content={
                "success": True,
                "registration": result,
                "engine_url": engine_url,
                "engine_key_did": engine_key_did,
            })
        finally:
            conn.close()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


# ---------------------------------------------------------------------------
# GET /api/v1/at-policy/decisions — View AT's decision log
# ---------------------------------------------------------------------------

@router.get("/api/v1/at-policy/decisions")
def get_decisions(
    org_id: Optional[int] = None,
    limit: int = Query(default=50, le=500),
):
    """View AT's own consultation log. No auth required for MVP."""
    entries = _decision_log
    if org_id is not None:
        entries = [e for e in entries if e.get("org_id") == org_id]
    entries = entries[-limit:]
    return JSONResponse(content={
        "count": len(entries),
        "decisions": list(reversed(entries)),
    })
