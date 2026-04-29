"""
ERC-8004 Event Indexer for Observer Protocol.

Watches Identity, Reputation, and Validation Registry events on Base
and TRON. Maintains a local PostgreSQL cache. Canonical truth lives
on-chain; indexer state is cache.

Indexed signals feed AT-ARS-1.0:
  - Boolean: agent has 8004 NFT on Base / TRON
  - Count: feedback entries received
  - Count: validation responses received
  - Boolean: feedback with proofOfPayment matching OP credential
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from contracts import get_chain_config, IDENTITY_REGISTRY_ABI, REPUTATION_REGISTRY_ABI

logger = logging.getLogger(__name__)

# ── Block range for log queries ──────────────────────────────
BLOCK_BATCH_SIZE = 2000  # Base produces ~2s blocks, so 2000 blocks ~ 1 hour
POLL_INTERVAL_SECONDS = 30


class ERC8004Indexer:
    """
    Indexes ERC-8004 registry events from Base (and TRON when contracts deploy).
    Designed to run as a background polling loop.
    """

    def __init__(self, get_db_connection, chain: str = "base"):
        self.get_db_connection = get_db_connection
        self.chain = chain
        self.config = get_chain_config(chain)
        if not self.config:
            raise ValueError(f"No config for chain: {chain}")

    def _rpc_call(self, method: str, params: list) -> dict:
        """Make an Ethereum JSON-RPC call."""
        resp = requests.post(self.config["rpc_url"], json={
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }, timeout=15)
        return resp.json()

    def _get_current_block(self) -> int:
        result = self._rpc_call("eth_blockNumber", [])
        return int(result.get("result", "0x0"), 16)

    def _get_last_indexed_block(self, registry_type: str) -> int:
        conn = self.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT last_indexed_block FROM erc8004_indexer_state WHERE chain = %s AND registry_type = %s",
                (self.chain, registry_type)
            )
            row = cur.fetchone()
            return row[0] if row else 0
        finally:
            cur.close()
            conn.close()

    def _update_last_indexed_block(self, registry_type: str, block: int):
        conn = self.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE erc8004_indexer_state
                SET last_indexed_block = %s, last_indexed_at = NOW(), error_count = 0
                WHERE chain = %s AND registry_type = %s
            """, (block, self.chain, registry_type))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def _record_error(self, registry_type: str, error: str):
        conn = self.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE erc8004_indexer_state
                SET error_count = error_count + 1, last_error = %s
                WHERE chain = %s AND registry_type = %s
            """, (error[:500], self.chain, registry_type))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def _get_logs(self, contract_address: str, from_block: int, to_block: int) -> list:
        """Fetch event logs from contract within block range."""
        if not contract_address:
            return []
        result = self._rpc_call("eth_getLogs", [{
            "address": contract_address,
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
        }])
        return result.get("result", [])

    # ── Identity Registry Indexing ───────────────────────────

    def index_identity_events(self):
        """Index Registered and URIUpdated events from Identity Registry."""
        contract = self.config.get("identity_registry")
        if not contract:
            return

        last_block = self._get_last_indexed_block("identity")
        current_block = self._get_current_block()
        if last_block >= current_block:
            return

        from_block = last_block + 1
        to_block = min(from_block + BLOCK_BATCH_SIZE, current_block)

        try:
            logs = self._get_logs(contract, from_block, to_block)
            conn = self.get_db_connection()
            cur = conn.cursor()

            for log in logs:
                topics = log.get("topics", [])
                if len(topics) < 1:
                    continue

                # Registered event (topic[0] matches)
                if len(topics) >= 3:
                    token_id = str(int(topics[1], 16)) if len(topics) > 1 else None
                    owner = "0x" + topics[2][-40:] if len(topics) > 2 else None
                    block_num = int(log.get("blockNumber", "0x0"), 16)

                    if token_id and owner:
                        cur.execute("""
                            INSERT INTO erc8004_agents
                                (chain, chain_id, token_id, owner_address, first_seen_block, last_updated_block)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (chain, token_id) DO UPDATE
                            SET owner_address = EXCLUDED.owner_address,
                                last_updated_block = EXCLUDED.last_updated_block,
                                updated_at = NOW()
                        """, (
                            self.chain, self.config["chain_id"], token_id,
                            owner, block_num, block_num,
                        ))

            conn.commit()
            cur.close()
            conn.close()
            self._update_last_indexed_block("identity", to_block)
            logger.info(f"Indexed identity events {from_block}-{to_block}: {len(logs)} logs")

        except Exception as e:
            logger.error(f"Identity indexing error: {e}")
            self._record_error("identity", str(e))

    # ── Reputation Registry Indexing ─────────────────────────

    def index_reputation_events(self):
        """Index NewFeedback and ResponseAppended events."""
        contract = self.config.get("reputation_registry")
        if not contract:
            return

        last_block = self._get_last_indexed_block("reputation")
        current_block = self._get_current_block()
        if last_block >= current_block:
            return

        from_block = last_block + 1
        to_block = min(from_block + BLOCK_BATCH_SIZE, current_block)

        try:
            logs = self._get_logs(contract, from_block, to_block)
            conn = self.get_db_connection()
            cur = conn.cursor()

            for log in logs:
                topics = log.get("topics", [])
                if len(topics) < 3:
                    continue

                token_id = str(int(topics[1], 16))
                client_address = "0x" + topics[2][-40:]
                block_num = int(log.get("blockNumber", "0x0"), 16)
                tx_hash = log.get("transactionHash", "")

                # Store feedback event
                cur.execute("""
                    INSERT INTO erc8004_feedback
                        (chain, chain_id, token_id, provider_address,
                         block_number, tx_hash)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (
                    self.chain, self.config["chain_id"], token_id,
                    client_address, block_num, tx_hash,
                ))

            conn.commit()
            cur.close()
            conn.close()
            self._update_last_indexed_block("reputation", to_block)
            logger.info(f"Indexed reputation events {from_block}-{to_block}: {len(logs)} logs")

        except Exception as e:
            logger.error(f"Reputation indexing error: {e}")
            self._record_error("reputation", str(e))

    # ── Validation Registry Indexing ─────────────────────────

    def index_validation_events(self):
        """Index ValidationRequest and ValidationResponse events."""
        contract = self.config.get("validation_registry")
        if not contract:
            return  # Not yet deployed

        last_block = self._get_last_indexed_block("validation")
        current_block = self._get_current_block()
        if last_block >= current_block:
            return

        from_block = last_block + 1
        to_block = min(from_block + BLOCK_BATCH_SIZE, current_block)

        try:
            logs = self._get_logs(contract, from_block, to_block)
            conn = self.get_db_connection()
            cur = conn.cursor()

            for log in logs:
                topics = log.get("topics", [])
                if len(topics) < 3:
                    continue

                validator_addr = "0x" + topics[1][-40:]
                token_id = str(int(topics[2], 16))
                block_num = int(log.get("blockNumber", "0x0"), 16)
                tx_hash = log.get("transactionHash", "")

                # Determine if this is a request or response based on topic count
                request_hash = topics[3] if len(topics) > 3 else None

                cur.execute("""
                    INSERT INTO erc8004_validations
                        (chain, chain_id, token_id, request_id,
                         validator_address, request_block, request_tx_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chain, request_id) DO NOTHING
                """, (
                    self.chain, self.config["chain_id"], token_id,
                    request_hash or tx_hash, validator_addr,
                    block_num, tx_hash,
                ))

            conn.commit()
            cur.close()
            conn.close()
            self._update_last_indexed_block("validation", to_block)
            logger.info(f"Indexed validation events {from_block}-{to_block}: {len(logs)} logs")

        except Exception as e:
            logger.error(f"Validation indexing error: {e}")
            self._record_error("validation", str(e))

    # ── Registration File Fetcher ────────────────────────────

    def fetch_registration_files(self):
        """
        For indexed agents without cached registration files,
        fetch the registration JSON from their tokenURI and parse
        for OP DID in the services array.
        """
        conn = self.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT id, token_id, registration_file_uri
                FROM erc8004_agents
                WHERE chain = %s AND registration_file_json IS NULL
                AND registration_file_uri IS NOT NULL
                LIMIT 50
            """, (self.chain,))

            for row in cur.fetchall():
                agent_db_id, token_id, uri = row
                try:
                    resp = requests.get(uri, timeout=10)
                    if resp.status_code == 200:
                        reg_file = resp.json()
                        op_did = self._extract_op_did(reg_file)
                        has_x402 = reg_file.get("x402Support", False)
                        active = reg_file.get("active", True)

                        cur.execute("""
                            UPDATE erc8004_agents
                            SET registration_file_json = %s,
                                op_did = %s,
                                has_x402_support = %s,
                                active = %s,
                                updated_at = NOW()
                            WHERE id = %s
                        """, (
                            json.dumps(reg_file), op_did,
                            has_x402, active, agent_db_id,
                        ))
                except Exception as e:
                    logger.warning(f"Failed to fetch reg file for token {token_id}: {e}")

            conn.commit()
        finally:
            cur.close()
            conn.close()

    def _extract_op_did(self, registration_file: dict) -> Optional[str]:
        """
        Extract OP DID from a registration file's services array.
        Looks for a service entry where name == "DID" and endpoint
        starts with "did:web:observerprotocol.org".
        """
        services = registration_file.get("services", [])
        for svc in services:
            if svc.get("name") == "DID":
                endpoint = svc.get("endpoint", "")
                if endpoint.startswith("did:web:"):
                    return endpoint
        return None

    # ── OP Credential Matching ───────────────────────────────

    def match_feedback_to_op_credentials(self):
        """
        For feedback entries with proofOfPayment, check if the hash
        matches any OP-issued credential. This is the high-value signal
        for AT-ARS: agents whose 8004 reputation is partially backed
        by OP-verifiable transactions.
        """
        conn = self.get_db_connection()
        cur = conn.cursor()
        try:
            # Get unmatched feedback entries that have proof of payment
            cur.execute("""
                SELECT f.id, f.feedback_file_json
                FROM erc8004_feedback f
                WHERE f.chain = %s
                AND f.has_proof_of_payment = TRUE
                AND f.matches_op_credential = FALSE
                AND f.feedback_file_json IS NOT NULL
                LIMIT 100
            """, (self.chain,))

            for row in cur.fetchall():
                fb_id, fb_json = row
                if isinstance(fb_json, str):
                    fb_json = json.loads(fb_json)

                proof_hash = fb_json.get("proofOfPayment", {}).get("hash")
                if not proof_hash:
                    continue

                # Check against x402 credentials
                cur.execute("""
                    SELECT credential_id FROM x402_credentials
                    WHERE settlement_tx_hash = %s
                    LIMIT 1
                """, (proof_hash,))
                match = cur.fetchone()

                if match:
                    cur.execute("""
                        UPDATE erc8004_feedback
                        SET matches_op_credential = TRUE,
                            matched_op_credential_id = %s
                        WHERE id = %s
                    """, (match[0], fb_id))

                    # Track for appendResponse trigger
                    provider = fb_json.get("provider", "unknown")
                    cur.execute("""
                        INSERT INTO erc8004_append_response_trigger
                            (partner_identifier, feedback_count, chain, first_match_at, last_match_at)
                        VALUES (%s, 1, %s, NOW(), NOW())
                        ON CONFLICT (partner_identifier, chain)
                        DO UPDATE SET
                            feedback_count = erc8004_append_response_trigger.feedback_count + 1,
                            last_match_at = NOW()
                    """, (provider, self.chain))

            conn.commit()
        finally:
            cur.close()
            conn.close()

    # ── AT-ARS Signal Update ─────────────────────────────────

    def update_agent_signals(self):
        """
        Update AT-ARS signal columns on observer_agents based on
        indexed 8004 data.
        """
        conn = self.get_db_connection()
        cur = conn.cursor()
        try:
            # Update has_8004_nft flags
            nft_column = "has_8004_nft_base" if self.chain == "base" else "has_8004_nft_tron"
            cur.execute(f"""
                UPDATE observer_agents oa
                SET {nft_column} = TRUE
                FROM erc8004_agents ea
                WHERE ea.op_agent_id = oa.agent_id
                AND ea.chain = %s
                AND ea.active = TRUE
            """, (self.chain,))

            # Update feedback and validation counts
            cur.execute("""
                UPDATE observer_agents oa
                SET erc8004_feedback_count = sub.cnt
                FROM (
                    SELECT ea.op_agent_id as agent_id, COUNT(*) as cnt
                    FROM erc8004_feedback ef
                    JOIN erc8004_agents ea ON ef.chain = ea.chain AND ef.token_id = ea.token_id
                    WHERE ef.chain = %s AND ea.op_agent_id IS NOT NULL
                    GROUP BY ea.op_agent_id
                ) sub
                WHERE oa.agent_id = sub.agent_id
            """, (self.chain,))

            # Update OP-backed feedback flag
            cur.execute("""
                UPDATE observer_agents oa
                SET erc8004_op_backed_feedback = TRUE
                FROM erc8004_feedback ef
                JOIN erc8004_agents ea ON ef.chain = ea.chain AND ef.token_id = ea.token_id
                WHERE ea.op_agent_id = oa.agent_id
                AND ef.matches_op_credential = TRUE
                AND ef.chain = %s
            """, (self.chain,))

            conn.commit()
        finally:
            cur.close()
            conn.close()

    # ── Main Poll Loop ───────────────────────────────────────

    def run_once(self):
        """Run one indexing cycle across all registries."""
        self.index_identity_events()
        self.index_reputation_events()
        self.index_validation_events()
        self.fetch_registration_files()
        self.match_feedback_to_op_credentials()
        self.update_agent_signals()

    def run_forever(self):
        """Polling loop. Run as a background thread or process."""
        logger.info(f"Starting 8004 indexer for {self.chain}")
        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Indexer cycle error: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)
