"""
Item C: Agent registration file pinning service.

Provides infrastructure to generate and serve 8004 registration files.
OP does NOT mint the ERC-721 NFT. The agent operator handles that
on-chain transaction. OP just provides the URL the tokenURI points to.

Two serving paths:
  1. HTTPS: <agent-domain>/.well-known/agent-registration.json
  2. OP-hosted fallback: agenticterminal.io/agents/<agent-id>/registration.json

Supports updates - when an agent's profile changes, regenerate and
republish at the same URL.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional

import psycopg2.extras

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'x402'))
from erc8004_hooks import generate_8004_registration_file


def generate_and_store_registration(
    conn,
    agent_id: str,
    agent_did: str,
    agent_name: str,
    description: str = "",
    image_url: str = "",
    a2a_endpoint: Optional[str] = None,
    mcp_endpoint: Optional[str] = None,
    web_endpoint: Optional[str] = None,
) -> dict:
    """
    Generate an 8004 registration file for an agent and store it
    for serving via the OP-hosted fallback path.

    Returns the registration file dict + serving URL.
    """
    # Check if agent has any x402 credentials (claim of fact, not capability)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM x402_credentials WHERE agent_id = %s",
        (agent_id,)
    )
    x402_count = cur.fetchone()[0]
    cur.close()

    reg_file = generate_8004_registration_file(
        agent_id=agent_id,
        agent_did=agent_did,
        agent_name=agent_name,
        description=description,
        image_url=image_url,
        a2a_endpoint=a2a_endpoint,
        mcp_endpoint=mcp_endpoint,
        web_endpoint=web_endpoint,
        has_x402_credentials=x402_count > 0,
    )

    # Compute content hash for integrity verification
    content = json.dumps(reg_file, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    # Store/update in database
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO erc8004_agent_registrations
                (agent_id, agent_did, registration_json, content_hash, created_at, updated_at)
            VALUES (%s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (agent_id)
            DO UPDATE SET
                registration_json = EXCLUDED.registration_json,
                content_hash = EXCLUDED.content_hash,
                updated_at = NOW()
        """, (agent_id, agent_did, json.dumps(reg_file), content_hash))
        conn.commit()
    finally:
        cur.close()

    serving_url = f"https://api.observerprotocol.org/agents/{agent_id}/registration.json"

    return {
        "registration_file": reg_file,
        "content_hash": content_hash,
        "serving_url": serving_url,
        "x402_credentials": x402_count,
    }


def get_registration_file(conn, agent_id: str) -> Optional[dict]:
    """Retrieve a stored registration file for serving."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT registration_json, content_hash, updated_at
            FROM erc8004_agent_registrations
            WHERE agent_id = %s
        """, (agent_id,))
        row = cur.fetchone()
        if row:
            reg = row["registration_json"]
            if isinstance(reg, str):
                reg = json.loads(reg)
            return {
                "registration_file": reg,
                "content_hash": row["content_hash"],
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
        return None
    finally:
        cur.close()
