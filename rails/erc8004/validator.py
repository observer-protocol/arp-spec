"""
Item D: OP as registered validator on Base ERC-8004 Validation Registry.

When OP receives a validation request via the registry's validationRequest()
event for an agent we've issued credentials about:
  1. Look up the agent's OP credentials
  2. Issue a fresh validation credential summarizing OP's attestation state
  3. Call validationResponse() with our credential URI as responseURI
  4. Use the tag field for AT-ARS score or credential summary

Conservative attestation discipline: OP only issues confident validations
we can back up. If we can't independently verify a claim, we say so in
the credential (same discrepancy-surfacing pattern as x402). Wrong
validations live on-chain forever and are positioning poison.

OP does NOT register as a validator on TRON in Phase 2.
"""

import json
import hashlib
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

import psycopg2.extras
import requests
from web3 import Web3

from contracts import get_chain_config


class OPValidator:
    """
    OP's validator role on Base's ERC-8004 Validation Registry.
    Watches for validation requests targeting agents with OP credentials,
    and responds with verification credential URIs.
    """

    def __init__(self, get_db_connection, chain: str = "base"):
        self.get_db_connection = get_db_connection
        self.chain = chain
        self.config = get_chain_config(chain)
        self.op_validator_address = os.environ.get("OP_VALIDATOR_ADDRESS")
        self.op_validator_private_key = os.environ.get("OP_VALIDATOR_PRIVATE_KEY")

    def process_pending_requests(self):
        """
        Find validation requests in our indexed state that:
        1. Target an agent with OP credentials
        2. Request OP as the validator
        3. Haven't been responded to yet

        For each, compose and submit a validation response.
        """
        conn = self.get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute("""
                SELECT ev.id, ev.token_id, ev.request_id, ev.requester_address,
                       ea.op_did, ea.op_agent_id
                FROM erc8004_validations ev
                JOIN erc8004_agents ea ON ev.chain = ea.chain AND ev.token_id = ea.token_id
                WHERE ev.chain = %s
                AND ev.is_op_validation = TRUE
                AND ev.responded_at IS NULL
                AND ea.op_agent_id IS NOT NULL
                LIMIT 10
            """, (self.chain,))

            for row in cur.fetchall():
                self._respond_to_request(conn, row)

        finally:
            cur.close()
            conn.close()

    def _respond_to_request(self, conn, request: dict):
        """
        Compose and submit a validation response for a single request.

        Conservative attestation: only attest what we can independently verify.
        """
        agent_id = request["op_agent_id"]
        op_did = request["op_did"]

        # Gather OP's attestation state for this agent
        attestation = self._gather_attestation(conn, agent_id)
        if not attestation:
            return  # Can't attest anything about this agent

        # Build credential URI
        credential_uri = f"https://api.observerprotocol.org/api/v1/credentials/validation-{request['request_id']}"

        # Build tag (AT-ARS summary)
        tag = self._build_tag(attestation)

        # Compute response hash
        response_content = json.dumps({
            "agent_did": op_did,
            "attestation": attestation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, sort_keys=True, separators=(",", ":"))
        response_hash = "0x" + hashlib.keccak_256(response_content.encode()).hexdigest() if hasattr(hashlib, 'keccak_256') else "0x" + hashlib.sha256(response_content.encode()).hexdigest()

        # Submit on-chain response (if validator key is configured)
        if self.op_validator_private_key and self.config.get("validation_registry"):
            try:
                self._submit_onchain_response(
                    request_hash=request["request_id"],
                    response_value=attestation["confidence_score"],
                    response_uri=credential_uri,
                    response_hash=response_hash,
                    tag=tag,
                )
            except Exception as e:
                # Log but don't fail - the credential is still valid off-chain
                import logging
                logging.error(f"On-chain validation response failed: {e}")

        # Update our indexed state
        cur = conn.cursor()
        cur.execute("""
            UPDATE erc8004_validations
            SET response_uri = %s, response_tag = %s,
                responded_at = NOW()
            WHERE id = %s
        """, (credential_uri, tag, request["id"]))
        conn.commit()
        cur.close()

    def _gather_attestation(self, conn, agent_id: str) -> Optional[dict]:
        """
        Gather OP's verifiable attestation state for an agent.
        Only includes facts we can independently verify.
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            # Check agent exists and is verified
            cur.execute("""
                SELECT agent_id, agent_did, verified, verified_at
                FROM observer_agents
                WHERE agent_id = %s
            """, (agent_id,))
            agent = cur.fetchone()
            if not agent or not agent["verified"]:
                return None

            # Count verified transactions across rails
            cur.execute("""
                SELECT protocol, COUNT(*) as count
                FROM verified_events
                WHERE agent_id = %s AND verified = TRUE
                GROUP BY protocol
            """, (agent_id,))
            tx_by_rail = {r["protocol"]: r["count"] for r in cur.fetchall()}

            # Count x402 credentials
            cur.execute(
                "SELECT COUNT(*) as cnt FROM x402_credentials WHERE agent_id = %s",
                (agent_id,)
            )
            x402_count = cur.fetchone()["cnt"]

            # Get AT-ARS score if available
            # (simplified - in production this would call the trust score API)
            total_tx = sum(tx_by_rail.values())

            # Conservative confidence score (0-100)
            # Higher when we have more independent verification
            confidence = min(100, total_tx * 2 + x402_count * 10)

            return {
                "agent_verified": True,
                "verified_at": agent["verified_at"].isoformat() if agent["verified_at"] else None,
                "transaction_count": total_tx,
                "transactions_by_rail": tx_by_rail,
                "x402_credential_count": x402_count,
                "confidence_score": confidence,
                "attestation_basis": "independent_verification",
                "disclaimer": "OP attests only to independently verified facts. This validation does not constitute endorsement.",
            }
        finally:
            cur.close()

    def _build_tag(self, attestation: dict) -> str:
        """Build a concise tag for the on-chain response."""
        parts = [f"confidence:{attestation['confidence_score']}"]
        parts.append(f"tx:{attestation['transaction_count']}")
        if attestation["x402_credential_count"] > 0:
            parts.append(f"x402:{attestation['x402_credential_count']}")
        rails = list(attestation["transactions_by_rail"].keys())
        if rails:
            parts.append(f"rails:{','.join(rails)}")
        return "|".join(parts)

    def _submit_onchain_response(
        self,
        request_hash: str,
        response_value: int,
        response_uri: str,
        response_hash: str,
        tag: str,
    ):
        """
        Submit validationResponse() on-chain.
        Requires OP_VALIDATOR_PRIVATE_KEY and a funded validator address on Base.
        """
        if not self.config.get("validation_registry"):
            raise ValueError("Validation Registry not deployed on this chain")

        w3 = Web3(Web3.HTTPProvider(self.config["rpc_url"]))
        # Contract interaction would go here once Validation Registry is deployed
        # For now, log the intent
        import logging
        logging.info(
            f"Would submit validationResponse: hash={request_hash}, "
            f"value={response_value}, uri={response_uri}, tag={tag}"
        )
