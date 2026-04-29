"""
Item F: appendResponse automation, built but disabled until trigger.

Watches indexed feedback entries. When a feedback entry includes a
proofOfPayment matching an OP-issued credential, composes and submits
an appendResponse() call with our verification credential URI.

DISABLED BY DEFAULT via erc8004_config['append_response_enabled'].

Trigger condition (locked, measurable):
  When 3 distinct design partners have each produced at least 5 feedback
  entries on Base or TRON 8004 Reputation Registries that include a
  proofOfPayment matching an OP-issued X402PaymentCredential (or successor),
  enable via config flip.

The point: when OP starts appearing on-chain as a verification authority,
it should be in response to real ecosystem activity, not us talking to ourselves.
"""

import json
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2.extras

logger = logging.getLogger(__name__)

# Trigger thresholds
PARTNER_COUNT_THRESHOLD = 3
FEEDBACK_PER_PARTNER_THRESHOLD = 5


class AppendResponseAutomation:
    """
    Watches for OP-credential-matched feedback entries and submits
    appendResponse on-chain. Disabled by default.
    """

    def __init__(self, get_db_connection, chain: str = "base"):
        self.get_db_connection = get_db_connection
        self.chain = chain

    def is_enabled(self) -> bool:
        """Check if appendResponse automation is enabled."""
        conn = self.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT value FROM erc8004_config WHERE key = 'append_response_enabled'"
            )
            row = cur.fetchone()
            return row and row[0] == 'true'
        finally:
            cur.close()
            conn.close()

    def check_trigger(self) -> dict:
        """
        Check progress toward the trigger condition.
        Returns status and progress details.
        """
        conn = self.get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute("""
                SELECT partner_identifier, feedback_count, chain,
                       first_match_at, last_match_at
                FROM erc8004_append_response_trigger
                WHERE feedback_count >= %s
            """, (FEEDBACK_PER_PARTNER_THRESHOLD,))
            qualified_partners = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT partner_identifier, feedback_count, chain
                FROM erc8004_append_response_trigger
                WHERE feedback_count < %s
            """, (FEEDBACK_PER_PARTNER_THRESHOLD,))
            in_progress_partners = [dict(r) for r in cur.fetchall()]

            triggered = len(qualified_partners) >= PARTNER_COUNT_THRESHOLD

            return {
                "triggered": triggered,
                "enabled": self.is_enabled(),
                "qualified_partners": len(qualified_partners),
                "required_partners": PARTNER_COUNT_THRESHOLD,
                "qualified": qualified_partners,
                "in_progress": in_progress_partners,
                "threshold_per_partner": FEEDBACK_PER_PARTNER_THRESHOLD,
            }
        finally:
            cur.close()
            conn.close()

    def enable(self):
        """Enable the automation (called when trigger fires)."""
        conn = self.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE erc8004_config
                SET value = 'true', updated_at = NOW()
                WHERE key = 'append_response_enabled'
            """)
            conn.commit()
            logger.info("appendResponse automation ENABLED")
        finally:
            cur.close()
            conn.close()

    def process_unresponded_feedback(self):
        """
        Find feedback entries with OP credential matches that we
        haven't yet responded to. Compose and submit appendResponse.

        Only runs if automation is enabled.
        """
        if not self.is_enabled():
            # Check if trigger should fire
            status = self.check_trigger()
            if status["triggered"] and not status["enabled"]:
                logger.info(
                    f"Trigger condition met: {status['qualified_partners']} partners "
                    f">= {PARTNER_COUNT_THRESHOLD}. Enabling automation."
                )
                self.enable()
            else:
                return

        conn = self.get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            # Find matched feedback we haven't responded to
            cur.execute("""
                SELECT f.id, f.chain, f.token_id, f.feedback_index,
                       f.provider_address, f.matched_op_credential_id,
                       f.feedback_file_json
                FROM erc8004_feedback f
                WHERE f.chain = %s
                AND f.matches_op_credential = TRUE
                AND f.id NOT IN (
                    SELECT feedback_id FROM erc8004_append_responses
                )
                LIMIT 10
            """, (self.chain,))

            for row in cur.fetchall():
                self._compose_and_submit_response(conn, row)

        finally:
            cur.close()
            conn.close()

    def _compose_and_submit_response(self, conn, feedback: dict):
        """
        Compose an appendResponse for a single feedback entry.

        Uses the matched OP credential as the response content.
        Conservative: response references the specific credential,
        not a blanket endorsement.
        """
        credential_id = feedback["matched_op_credential_id"]
        if not credential_id:
            return

        # Build response URI pointing to our public credential endpoint
        clean_id = credential_id.replace("urn:uuid:", "")
        response_uri = f"https://api.observerprotocol.org/api/v1/credentials/{clean_id}"

        # Compute response hash
        response_content = json.dumps({
            "credential_id": credential_id,
            "chain": feedback["chain"],
            "token_id": feedback["token_id"],
            "verified_by": "did:web:observerprotocol.org",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, sort_keys=True, separators=(",", ":"))
        response_hash = hashlib.sha256(response_content.encode()).hexdigest()

        # Log the response (on-chain submission would go here when
        # Reputation Registry appendResponse is callable)
        logger.info(
            f"appendResponse composed for feedback {feedback['id']}: "
            f"credential={credential_id}, uri={response_uri}"
        )

        # Record that we've processed this feedback
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO erc8004_append_responses
                    (feedback_id, credential_id, response_uri, response_hash, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
            """, (feedback["id"], credential_id, response_uri, response_hash))
            conn.commit()
        finally:
            cur.close()
