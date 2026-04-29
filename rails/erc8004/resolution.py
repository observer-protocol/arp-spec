"""
Item B: Cross-registry identity resolution.

Two-direction lookup:
  - Given OP did:web, find associated 8004 NFTs across Base + TRON
  - Given 8004 NFT (chain + token ID), resolve to OP DID

Uses indexed state from the 8004 indexer (PostgreSQL cache).
"""

import json
from typing import Optional

import psycopg2.extras


def resolve_did_to_8004(conn, did_web: str) -> list:
    """
    Given an OP did:web, find any associated 8004 NFTs.

    Discovery: scan indexed registration files for a services array
    entry where name == "DID" and endpoint == queried did:web.

    Returns list of {chain, chain_id, token_id, owner_address, active, x402Support}.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT chain, chain_id, token_id, owner_address,
                   active, has_x402_support, registration_file_uri
            FROM erc8004_agents
            WHERE op_did = %s
        """, (did_web,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()


def resolve_8004_to_did(conn, chain: str, token_id: str) -> Optional[dict]:
    """
    Given an 8004 NFT (chain + token ID), resolve its registration
    file and return the OP DID if present.

    Returns {op_did, op_agent_id, registration_file} or None.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT op_did, op_agent_id, registration_file_json,
                   owner_address, active, has_x402_support
            FROM erc8004_agents
            WHERE chain = %s AND token_id = %s
        """, (chain, token_id))
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        cur.close()


def get_agent_8004_summary(conn, agent_id: str) -> dict:
    """
    Get a summary of an agent's 8004 presence across all chains.
    Used by AT-ARS and demo tooling.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT chain, chain_id, token_id, owner_address, active,
                   has_x402_support, registration_file_uri
            FROM erc8004_agents
            WHERE op_agent_id = %s
        """, (agent_id,))
        nfts = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT COUNT(*) as feedback_count,
                   COUNT(*) FILTER (WHERE matches_op_credential) as op_backed_count
            FROM erc8004_feedback ef
            JOIN erc8004_agents ea ON ef.chain = ea.chain AND ef.token_id = ea.token_id
            WHERE ea.op_agent_id = %s
        """, (agent_id,))
        feedback = dict(cur.fetchone() or {"feedback_count": 0, "op_backed_count": 0})

        cur.execute("""
            SELECT COUNT(*) as validation_count,
                   COUNT(*) FILTER (WHERE is_op_validation) as op_validation_count
            FROM erc8004_validations ev
            JOIN erc8004_agents ea ON ev.chain = ea.chain AND ev.token_id = ea.token_id
            WHERE ea.op_agent_id = %s
        """, (agent_id,))
        validations = dict(cur.fetchone() or {"validation_count": 0, "op_validation_count": 0})

        return {
            "agent_id": agent_id,
            "nfts": nfts,
            "has_8004_presence": len(nfts) > 0,
            "feedback": feedback,
            "validations": validations,
        }
    finally:
        cur.close()
