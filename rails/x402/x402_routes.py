"""
x402 API routes for Observer Protocol.

Endpoints:
  POST /api/v1/x402/verify     - Verify an x402 payment and issue X402PaymentCredential
  GET  /api/v1/x402/credentials/{agent_id} - List x402 credentials for an agent
"""

import json
from datetime import datetime, timezone
from typing import Optional

import psycopg2.extras
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/x402", tags=["x402"])

_get_db_connection = None


def configure(get_db_connection_fn):
    global _get_db_connection
    _get_db_connection = get_db_connection_fn


class X402VerifyRequest(BaseModel):
    agent_id: str
    agent_did: str
    counterparty: str
    payment_scheme: str = "exact"
    network: str = "eip155:8453"
    asset_address: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    asset_symbol: str = "USDC"
    amount: str
    resource_uri: str
    facilitator_url: str = "https://x402.coinbase.com"
    settlement_tx_hash: str
    payment_payload: dict


@router.post("/verify")
def verify_x402_payment(req: X402VerifyRequest):
    """
    Verify an x402 payment and issue an X402PaymentCredential.

    Dual verification:
      1. Coinbase facilitator endpoint (primary)
      2. Base RPC on-chain USDC transfer (ground truth)

    If both pass: credential with discrepancy=false.
    If only one passes: credential issued with discrepancy=true (surfaced, not hidden).
    If neither passes: 400 error.
    """
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

    from x402_adapter import verify_and_attest

    try:
        result = verify_and_attest(
            agent_did=req.agent_did,
            agent_id=req.agent_id,
            counterparty=req.counterparty,
            payment_scheme=req.payment_scheme,
            network=req.network,
            asset_address=req.asset_address,
            asset_symbol=req.asset_symbol,
            amount=req.amount,
            resource_uri=req.resource_uri,
            facilitator_url=req.facilitator_url,
            settlement_tx_hash=req.settlement_tx_hash,
            payment_payload=req.payment_payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Store credential in DB
    conn = _get_db_connection()
    cur = conn.cursor()
    try:
        vc = result["credential"]
        cur.execute("""
            INSERT INTO x402_credentials
                (credential_id, agent_id, agent_did, counterparty, network,
                 asset_symbol, amount, resource_uri, settlement_tx_hash,
                 facilitator_verified, onchain_verified, discrepancy,
                 credential_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            vc.get("id"), req.agent_id, req.agent_did, req.counterparty,
            req.network, req.asset_symbol, req.amount, req.resource_uri,
            req.settlement_tx_hash,
            result["verification"]["facilitator_verified"],
            result["verification"]["onchain_verified"],
            result["verification"]["discrepancy"],
            json.dumps(vc),
        ))

        # Also insert into verified_events for AT-ARS integration
        import uuid as _uuid
        event_id = f"event-x402-{_uuid.uuid4().hex[:12]}"
        cur.execute("""
            INSERT INTO verified_events
                (event_id, agent_id, event_type, protocol, transaction_hash,
                 time_window, amount_bucket, amount_sats, direction,
                 verified, created_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """, (
            event_id, req.agent_id, "payment.executed", "x402",
            req.settlement_tx_hash,
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            _classify_amount(req.amount, req.asset_symbol),
            0,  # amount_sats is 0 for x402 — actual amount is in metadata.amount_usdc
            "outbound",
            True,
            json.dumps({
                "asset": req.asset_symbol,
                "amount_usdc": _format_usdc(req.amount),
                "network": req.network,
                "resource": req.resource_uri,
                "x402_credential_id": vc.get("id"),
            }),
        ))

        conn.commit()

        return {
            "credential": vc,
            "verification": result["verification"],
            "event_id": event_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/credentials/{agent_id}")
def get_x402_credentials(agent_id: str, limit: int = 20):
    """List X402PaymentCredentials for an agent."""
    conn = _get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT credential_id, counterparty, network, asset_symbol, amount,
                   resource_uri, settlement_tx_hash, facilitator_verified,
                   onchain_verified, discrepancy, created_at
            FROM x402_credentials
            WHERE agent_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (agent_id, limit))
        rows = cur.fetchall()
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].isoformat()
        return {"agent_id": agent_id, "credentials": [dict(r) for r in rows], "count": len(rows)}
    finally:
        cur.close()
        conn.close()


def _classify_amount(amount_atomic: str, symbol: str) -> str:
    """Classify amount into bucket for AT-ARS."""
    try:
        if symbol == "USDC":
            usd = int(amount_atomic) / 1_000_000
        else:
            usd = float(amount_atomic)
        if usd < 1:
            return "micro"
        elif usd < 100:
            return "medium"
        else:
            return "large"
    except (ValueError, ZeroDivisionError):
        return "medium"


def _format_usdc(amount_atomic: str) -> str:
    """Format atomic USDC amount to human-readable."""
    try:
        return f"{int(amount_atomic) / 1_000_000:.2f}"
    except (ValueError, ZeroDivisionError):
        return amount_atomic
