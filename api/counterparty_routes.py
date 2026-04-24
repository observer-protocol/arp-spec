"""
Spec 3.6 — Counterparty Management endpoints.

5 endpoints:
  GET    /api/v1/counterparties                        — list (viewer+)
  GET    /api/v1/counterparties/{counterparty_id}      — detail (viewer+)
  POST   /api/v1/counterparties/accept                 — accept (operator+)
  POST   /api/v1/counterparties/{counterparty_id}/revoke — revoke (operator+)
  PATCH  /api/v1/counterparties/{counterparty_id}      — update metadata (operator+)
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse

from counterparty_store import (
    list_counterparties,
    get_counterparty,
    accept_counterparty,
    revoke_counterparty,
    update_counterparty_metadata,
)

router = APIRouter()

_get_db_connection = None
_validate_session = None


def configure(get_db_connection_fn, validate_session_fn):
    global _get_db_connection, _validate_session
    _get_db_connection = get_db_connection_fn
    _validate_session = validate_session_fn


def _require_configured():
    if _get_db_connection is None:
        raise RuntimeError("counterparty_routes not configured")


# ---------------------------------------------------------------------------
# GET /api/v1/counterparties
# ---------------------------------------------------------------------------

@router.get("/api/v1/counterparties")
def list_counterparties_endpoint(
    request: Request,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List counterparties for the session's org."""
    _require_configured()
    from role_enforcement import require_role
    _, org_id, _, _ = require_role(_validate_session(request), "viewer")

    if status and status not in ("observed", "accepted", "revoked"):
        raise HTTPException(status_code=400, detail="status must be observed, accepted, or revoked")

    conn = _get_db_connection()
    try:
        result = list_counterparties(conn, org_id, status=status, limit=limit, offset=offset)
        return JSONResponse(content=result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/v1/counterparties/{counterparty_id}
# ---------------------------------------------------------------------------

@router.get("/api/v1/counterparties/{counterparty_id}")
def get_counterparty_endpoint(counterparty_id: int, request: Request):
    """Get counterparty detail."""
    _require_configured()
    from role_enforcement import require_role
    _, org_id, _, _ = require_role(_validate_session(request), "viewer")

    conn = _get_db_connection()
    try:
        cp = get_counterparty(conn, counterparty_id, org_id)
        if not cp:
            raise HTTPException(status_code=404, detail="Counterparty not found")

        # Add profile URL for frontend deep-linking
        did = cp.get("counterparty_did", "")
        # Extract agent_id from DID if possible, otherwise use address as-is
        if "/agents/" in did:
            agent_id_hash = did.split("/agents/")[-1]
        else:
            agent_id_hash = did
        cp["profile_url"] = f"/agents/{agent_id_hash}"

        return JSONResponse(content=cp)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/v1/counterparties/accept
# ---------------------------------------------------------------------------

@router.post("/api/v1/counterparties/accept")
async def accept_counterparty_endpoint(request: Request):
    """Accept a counterparty. Creates row if not exists."""
    _require_configured()
    from role_enforcement import require_role
    user_id, org_id, _, _ = require_role(_validate_session(request), "operator")

    body = await request.json()
    counterparty_did = body.get("counterparty_did")
    if not counterparty_did:
        raise HTTPException(status_code=400, detail="counterparty_did required")

    conn = _get_db_connection()
    try:
        result = accept_counterparty(
            conn, org_id, counterparty_did, user_id,
            tag=body.get("tag"), notes=body.get("notes"),
        )
        return JSONResponse(content=result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/v1/counterparties/{counterparty_id}/revoke
# ---------------------------------------------------------------------------

@router.post("/api/v1/counterparties/{counterparty_id}/revoke")
async def revoke_counterparty_endpoint(counterparty_id: int, request: Request):
    """Revoke counterparty acceptance. Forward-looking only."""
    _require_configured()
    from role_enforcement import require_role
    user_id, org_id, _, _ = require_role(_validate_session(request), "operator")

    body = await request.json()

    conn = _get_db_connection()
    try:
        result = revoke_counterparty(
            conn, counterparty_id, org_id, user_id,
            reason=body.get("reason"),
        )
        if not result:
            raise HTTPException(status_code=404, detail="Counterparty not found")
        return JSONResponse(content=result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# PATCH /api/v1/counterparties/{counterparty_id}
# ---------------------------------------------------------------------------

@router.patch("/api/v1/counterparties/{counterparty_id}")
async def update_counterparty_endpoint(counterparty_id: int, request: Request):
    """Update counterparty metadata (tag, notes). Does not change status."""
    _require_configured()
    from role_enforcement import require_role
    _, org_id, _, _ = require_role(_validate_session(request), "operator")

    body = await request.json()

    conn = _get_db_connection()
    try:
        result = update_counterparty_metadata(
            conn, counterparty_id, org_id,
            tag=body.get("tag"), notes=body.get("notes"),
        )
        if not result:
            raise HTTPException(status_code=404, detail="Counterparty not found")
        return JSONResponse(content=result)
    finally:
        conn.close()
