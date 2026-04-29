"""
ERC-8004 API routes for Observer Protocol.

Exposes cross-registry resolution, agent registration pinning,
8004 summary, and trigger status.
"""

import json
from typing import Optional

import psycopg2.extras
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/erc8004", tags=["erc8004"])

_get_db_connection = None


def configure(get_db_connection_fn):
    global _get_db_connection
    _get_db_connection = get_db_connection_fn


# ── Models ───────────────────────────────────────────────────

class PinRegistrationRequest(BaseModel):
    agent_id: str
    agent_did: str
    agent_name: str
    description: Optional[str] = ""
    image_url: Optional[str] = ""
    a2a_endpoint: Optional[str] = None
    mcp_endpoint: Optional[str] = None
    web_endpoint: Optional[str] = None


# ── Cross-Registry Resolution (Item B) ──────────────────────

@router.get("/resolve/did/{did_web:path}")
def resolve_did_to_nfts(did_web: str):
    """Given an OP did:web, find associated 8004 NFTs."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from resolution import resolve_did_to_8004

    conn = _get_db_connection()
    try:
        nfts = resolve_did_to_8004(conn, did_web)
        return {"did": did_web, "nfts": nfts, "count": len(nfts)}
    finally:
        conn.close()


@router.get("/resolve/nft/{chain}/{token_id}")
def resolve_nft_to_did(chain: str, token_id: str):
    """Given an 8004 NFT, resolve to OP DID."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from resolution import resolve_8004_to_did

    conn = _get_db_connection()
    try:
        result = resolve_8004_to_did(conn, chain, token_id)
        if not result:
            raise HTTPException(status_code=404, detail="NFT not found in index")
        return result
    finally:
        conn.close()


@router.get("/agent/{agent_id}/summary")
def get_agent_8004_summary(agent_id: str):
    """Get an agent's full 8004 presence summary."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from resolution import get_agent_8004_summary as _get_summary

    conn = _get_db_connection()
    try:
        return _get_summary(conn, agent_id)
    finally:
        conn.close()


# ── Registration File Pinning (Item C) ───────────────────────

@router.post("/registration/pin")
def pin_registration_file(req: PinRegistrationRequest):
    """Generate and store an 8004 registration file for an agent."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from pinning import generate_and_store_registration

    conn = _get_db_connection()
    try:
        result = generate_and_store_registration(
            conn,
            agent_id=req.agent_id,
            agent_did=req.agent_did,
            agent_name=req.agent_name,
            description=req.description,
            image_url=req.image_url,
            a2a_endpoint=req.a2a_endpoint,
            mcp_endpoint=req.mcp_endpoint,
            web_endpoint=req.web_endpoint,
        )
        return result
    finally:
        conn.close()


@router.get("/registration/{agent_id}")
def get_registration_file(agent_id: str):
    """Serve a stored registration file (OP-hosted fallback path)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from pinning import get_registration_file as _get_reg

    conn = _get_db_connection()
    try:
        result = _get_reg(conn, agent_id)
        if not result:
            raise HTTPException(status_code=404, detail="No registration file for this agent")
        return result["registration_file"]
    finally:
        conn.close()


# ── appendResponse Trigger Status (Item F) ───────────────────

@router.get("/trigger/append-response")
def get_trigger_status():
    """Check progress toward the appendResponse trigger."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from append_response import AppendResponseAutomation

    automation = AppendResponseAutomation(_get_db_connection)
    return automation.check_trigger()


# ── Indexer Status ───────────────────────────────────────────

@router.get("/indexer/status")
def get_indexer_status():
    """Get current indexer state across all chains and registries."""
    conn = _get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM erc8004_indexer_state ORDER BY chain, registry_type")
        states = [dict(r) for r in cur.fetchall()]
        for s in states:
            if s.get("last_indexed_at"):
                s["last_indexed_at"] = s["last_indexed_at"].isoformat()

        cur.execute("SELECT COUNT(*) as cnt FROM erc8004_agents")
        agent_count = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) as cnt FROM erc8004_feedback")
        feedback_count = cur.fetchone()["cnt"]

        return {
            "indexer_state": states,
            "indexed_agents": agent_count,
            "indexed_feedback": feedback_count,
        }
    finally:
        cur.close()
        conn.close()
