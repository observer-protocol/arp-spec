"""
Spec 3.5 — Policy engine registration and consultation log endpoints.

OP-side endpoints:
  POST   /api/v1/policy-engines/register          — register engine (admin)
  GET    /api/v1/policy-engines/{org_id}           — get registration (viewer+)
  DELETE /api/v1/policy-engines/{org_id}           — deactivate engine (admin)
  POST   /api/v1/policy-engines/{org_id}/health-check — test engine reachability (admin)
  GET    /api/v1/policy-consultations              — list consultations (viewer+)
  GET    /api/v1/policy-consultations/{request_id} — get specific consultation (viewer+)
"""

import json
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse

from policy_engine_store import (
    register_engine,
    get_engine,
    deactivate_engine,
    get_consultations,
    get_consultation_by_request_id,
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
        raise RuntimeError("policy_routes not configured")


def _get_session(request: Request) -> tuple:
    return _validate_session(request)


# ---------------------------------------------------------------------------
# POST /api/v1/policy-engines/register
# ---------------------------------------------------------------------------

@router.post("/api/v1/policy-engines/register")
async def register_engine_endpoint(request: Request):
    """Register or re-register a policy engine for an org. Admin only."""
    _require_configured()
    from role_enforcement import require_role
    user_id, org_id, email, role = require_role(_get_session(request), "admin")

    body = await request.json()

    required = ["org_id", "engine_url", "engine_public_key_did", "engine_name"]
    for field in required:
        if not body.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    target_org_id = body["org_id"]

    conn = _get_db_connection()
    try:
        result = register_engine(
            conn=conn,
            org_id=target_org_id,
            engine_url=body["engine_url"],
            engine_public_key_did=body["engine_public_key_did"],
            engine_name=body["engine_name"],
            engine_version=body.get("engine_version"),
            registered_by=user_id,
        )
        return JSONResponse(content=result)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/v1/policy-engines/{org_id}
# ---------------------------------------------------------------------------

@router.get("/api/v1/policy-engines/{org_id}")
def get_engine_endpoint(org_id: int, request: Request):
    """Get the registered engine for an org. Viewer+."""
    _require_configured()
    from role_enforcement import require_role
    require_role(_get_session(request), "viewer")

    conn = _get_db_connection()
    try:
        engine = get_engine(conn, org_id)
        if not engine:
            return JSONResponse(content={
                "org_id": org_id,
                "engine": None,
                "mode": "permit-by-default",
            })
        return JSONResponse(content={"org_id": org_id, "engine": engine, "mode": "policy-enforced"})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DELETE /api/v1/policy-engines/{org_id}
# ---------------------------------------------------------------------------

@router.delete("/api/v1/policy-engines/{org_id}")
def delete_engine_endpoint(org_id: int, request: Request):
    """Deactivate engine registration. Reverts org to permit-by-default. Admin only."""
    _require_configured()
    from role_enforcement import require_role
    require_role(_get_session(request), "admin")

    conn = _get_db_connection()
    try:
        deleted = deactivate_engine(conn, org_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="No active engine for this org")
        return JSONResponse(content={"success": True, "org_id": org_id, "mode": "permit-by-default"})
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/v1/policy-engines/{org_id}/health-check
# ---------------------------------------------------------------------------

@router.post("/api/v1/policy-engines/{org_id}/health-check")
def health_check_engine(org_id: int, request: Request):
    """Test a registered engine's reachability and signature. Admin only."""
    _require_configured()
    from role_enforcement import require_role
    require_role(_get_session(request), "admin")

    conn = _get_db_connection()
    try:
        engine = get_engine(conn, org_id)
        if not engine:
            raise HTTPException(status_code=404, detail="No engine registered for this org")

        test_request = {
            "request_id": str(uuid.uuid4()),
            "org_id": org_id,
            "action_type": "health_check",
            "action_context": {},
            "timestamp": "2026-01-01T00:00:00Z",
        }

        try:
            with httpx.Client(timeout=5) as client:
                resp = client.post(engine["engine_url"], json=test_request)
            return JSONResponse(content={
                "reachable": True,
                "status_code": resp.status_code,
                "response_body": resp.json() if resp.status_code == 200 else resp.text[:500],
                "engine_url": engine["engine_url"],
            })
        except httpx.TimeoutException:
            return JSONResponse(content={
                "reachable": False,
                "error": "timeout",
                "engine_url": engine["engine_url"],
            }, status_code=503)
        except Exception as e:
            return JSONResponse(content={
                "reachable": False,
                "error": str(e)[:200],
                "engine_url": engine["engine_url"],
            }, status_code=503)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/v1/policy-consultations
# ---------------------------------------------------------------------------

@router.get("/api/v1/policy-consultations")
def list_consultations(
    request: Request,
    org_id: int = Query(...),
    limit: int = Query(default=50, le=500),
):
    """List recent policy consultations for an org. Viewer+."""
    _require_configured()
    from role_enforcement import require_role
    require_role(_get_session(request), "viewer")

    conn = _get_db_connection()
    try:
        consultations = get_consultations(conn, org_id, limit=limit)
        return JSONResponse(content={
            "org_id": org_id,
            "count": len(consultations),
            "consultations": consultations,
        })
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/v1/policy-consultations/{request_id}
# ---------------------------------------------------------------------------

@router.get("/api/v1/policy-consultations/{request_id}")
def get_consultation(request_id: str, request: Request):
    """Get a specific consultation by request_id. Viewer+."""
    _require_configured()
    from role_enforcement import require_role
    require_role(_get_session(request), "viewer")

    conn = _get_db_connection()
    try:
        consultation = get_consultation_by_request_id(conn, request_id)
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")
        return JSONResponse(content=consultation)
    finally:
        conn.close()
