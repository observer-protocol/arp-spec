"""
ERC-8004 Forward-Compatibility Hooks for Observer Protocol.

These hooks exist in Phase 1 to ensure Phase 2 (full 8004 integration)
is a connector job, not a refactor. None of these are called in
production in Phase 1. They are tested and ready for Phase 2 wiring.

Hooks:
  1. CAIP-10 expressibility (agent records)
  2. 8004 registration file generator
  3. AT-ARS feedback-entry-shaped serializer
  4. VC URI addressability (public credential endpoints)
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional


# ── Hook 1: CAIP-10 Expressibility ───────────────────────────

def agent_to_caip10(
    chain_namespace: str,
    chain_reference: str,
    account_address: str,
) -> str:
    """
    Express an agent identity as a CAIP-10 account identifier.

    CAIP-10 is the bridge format for on-chain registries, not a replacement
    for did:web. did:web remains canonical OP identity. CAIP-10 identifiers
    are per-agent wallet anchors stored for the purpose of interacting with
    8004 contracts that expect wallet address format.

    Examples:
      eip155:8453:0xabc...  (Base mainnet)
      tron:mainnet:Tabc...  (TRON mainnet)
    """
    return f"{chain_namespace}:{chain_reference}:{account_address}"


def add_caip10_to_agent(conn, agent_id: str, caip10_id: str) -> None:
    """
    Add a CAIP-10 identifier to an agent's record.

    The caip10_identifiers column is a JSONB array. Multiple
    CAIP-10 identifiers are supported (multi-chain agents).
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE observer_agents
            SET caip10_identifiers = COALESCE(caip10_identifiers, '[]'::jsonb) || %s::jsonb
            WHERE agent_id = %s
            AND NOT (COALESCE(caip10_identifiers, '[]'::jsonb) @> %s::jsonb)
        """, (json.dumps([caip10_id]), agent_id, json.dumps([caip10_id])))
        conn.commit()
    finally:
        cur.close()


# ── Hook 2: 8004 Registration File Generator ────────────────

def generate_8004_registration_file(
    agent_id: str,
    agent_did: str,
    agent_name: str,
    description: str = "",
    image_url: str = "",
    a2a_endpoint: Optional[str] = None,
    mcp_endpoint: Optional[str] = None,
    web_endpoint: Optional[str] = None,
    has_x402_credentials: bool = False,
) -> dict:
    """
    Generate an ERC-8004-compliant registration file for an agent.

    x402Support is true ONLY when the agent has at least one issued
    X402PaymentCredential (claim of fact, not claim of capability).

    References the canonical ERC-8004 spec and M2M Registry contracts
    (BofAI deployment) for TRC-8004 on TRON. No AINFT SDK dependency.

    This file is NOT published to IPFS or uploaded to any registry
    in Phase 1. Phase 2 will pin it and reference it from on-chain
    registrations (OP as validator on Base's Validation Registry).
    """
    services = [
        {
            "name": "DID",
            "endpoint": agent_did,
            "version": "v1",
        }
    ]

    if a2a_endpoint:
        services.append({
            "name": "A2A",
            "endpoint": a2a_endpoint,
            "version": "v1",
        })

    if mcp_endpoint:
        services.append({
            "name": "MCP",
            "endpoint": mcp_endpoint,
            "version": "v1",
        })

    if web_endpoint:
        services.append({
            "name": "Web",
            "endpoint": web_endpoint,
            "version": "v1",
        })

    registration_file = {
        "name": agent_name,
        "description": description or f"Observer Protocol agent: {agent_name}",
        "image": image_url,
        "services": services,
        "x402Support": has_x402_credentials,
        "active": True,
        "registrations": [],  # Populated in Phase 2 when registered on-chain
        "metadata": {
            "protocol": "observer-protocol",
            "did": agent_did,
            "agent_id": agent_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    return registration_file


# ── Hook 3: AT-ARS Feedback-Entry Serializer ─────────────────

def transaction_to_8004_feedback(
    agent_did: str,
    counterparty_did: str,
    transaction_type: str,
    rail: str,
    amount: str,
    currency: str,
    verified: bool,
    timestamp: str,
    credential_id: Optional[str] = None,
) -> dict:
    """
    Serialize an AT-ARS-1.0 transaction event into the shape of an
    ERC-8004 Reputation Registry giveFeedback entry.

    The 8004 Reputation Registry's giveFeedback interface takes
    structured feedback signals. This serializer ensures AT-ARS's
    per-transaction events can be expressed in that shape.

    This serializer is NOT called by anything in Phase 1. It exists,
    tested, ready for Phase 2 to wire up to on-chain registry writes.
    """
    # Compute a deterministic signal ID from the transaction
    signal_content = f"{agent_did}:{counterparty_did}:{timestamp}:{amount}"
    signal_hash = hashlib.sha256(signal_content.encode()).hexdigest()

    feedback_entry = {
        # 8004 Reputation Registry fields
        "agentId": agent_did,
        "feedbackProvider": counterparty_did,
        "timestamp": timestamp,
        "signalType": "transaction_verification",
        "signalPayload": {
            "transactionType": transaction_type,
            "rail": rail,
            "amount": amount,
            "currency": currency,
            "verified": verified,
            "verificationMethod": "observer_protocol_dual_verification",
        },
        "signalHash": signal_hash,
        # OP-specific extensions (ignored by 8004 but useful for auditing)
        "_op_credential_id": credential_id,
        "_op_rail": rail,
    }

    return feedback_entry


# ── Hook 4: VC URI Addressability ────────────────────────────

def credential_public_uri(credential_id: str, base_url: str = "https://api.observerprotocol.org") -> str:
    """
    Generate a stable, public URI for a credential.

    This URI is what gets posted to the 8004 Validation Registry
    in Phase 2 as the validationDataURI / responseURI.

    The credential must be retrievable at this URI without authentication.
    """
    # Strip urn:uuid: prefix if present
    clean_id = credential_id.replace("urn:uuid:", "")
    return f"{base_url}/api/v1/credentials/{clean_id}"
