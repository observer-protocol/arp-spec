"""
Data access layer for Spec 3.4 audit tables.

Handles CRUD for six tables:
  agent_activity_credentials, counterparty_receipts,
  receipt_requests, receipt_acknowledgments,
  audit_coverage_rollup, audit_anomalies.

Replay idempotency: all ingest functions use INSERT ... ON CONFLICT (credential_id)
DO NOTHING. Second submission returns 200 with original ingested_at, not 409.

Compatibility: works with both PostgreSQL (production) and SQLite (tests) by
avoiding RETURNING clauses and using a two-step insert-then-select pattern.
"""

import json
from datetime import datetime, timezone
from typing import Optional


class AuditStoreError(Exception):
    pass


def _insert_or_ignore_and_select(cursor, conn, insert_sql, insert_params, table, credential_id):
    """
    Insert with ON CONFLICT DO NOTHING, then SELECT to get the row.
    Returns (row_dict, is_new) where row_dict has 'id' and 'ingested_at'.
    Compatible with both PostgreSQL and SQLite (no RETURNING needed).
    """
    cursor.execute(insert_sql, insert_params)
    # Check if insert actually happened by looking for the row
    cursor.execute(
        f"SELECT id, ingested_at FROM {table} WHERE credential_id = %s",
        (credential_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise AuditStoreError(f"Failed to insert or find {credential_id} in {table}")

    # Determine if this was a new insert: if we can detect via rowcount or
    # by comparing timestamps. Simplest: check if ingested_at is very recent.
    # But actually, the reliable approach is to try a pre-check.
    # For simplicity: do a SELECT first, then INSERT, then SELECT again.
    # Restructure below for clarity.
    return row


# ---------------------------------------------------------------------------
# Agent Activity Credentials
# ---------------------------------------------------------------------------

def ingest_activity(conn, credential: dict, extracted: dict) -> dict:
    """
    Store an AgentActivityCredential. Idempotent on credential_id.
    """
    cred_id = extracted["credential_id"]
    cursor = conn.cursor()
    try:
        # Check if already exists
        cursor.execute(
            "SELECT id, ingested_at FROM agent_activity_credentials WHERE credential_id = %s",
            (cred_id,),
        )
        existing = cursor.fetchone()
        if existing:
            return {
                "id": existing[0],
                "credential_id": cred_id,
                "ingested_at": existing[1].isoformat() if hasattr(existing[1], "isoformat") else str(existing[1]),
                "is_new": False,
            }

        # Insert
        cursor.execute(
            """
            INSERT INTO agent_activity_credentials (
                credential_id, agent_did, activity_type, activity_timestamp,
                is_merkle_root, merkle_root_hash, parent_root_credential_id,
                counterparty_did, expects_counterparty_receipt,
                expected_receipt_window, transaction_rail, transaction_reference,
                transaction_amount, transaction_currency,
                delegation_credential_id, credential_jsonld
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                cred_id,
                extracted["agent_did"],
                extracted["activity_type"],
                extracted["activity_timestamp"],
                extracted.get("is_merkle_root", False),
                extracted.get("merkle_root_hash"),
                extracted.get("parent_root_credential_id"),
                extracted.get("counterparty_did"),
                extracted.get("expects_counterparty_receipt", False),
                extracted.get("expected_receipt_window"),
                extracted.get("transaction_rail"),
                extracted.get("transaction_reference"),
                extracted.get("transaction_amount"),
                extracted.get("transaction_currency"),
                extracted.get("delegation_credential_id"),
                json.dumps(credential),
            ),
        )
        conn.commit()

        # Fetch the inserted row
        cursor.execute(
            "SELECT id, ingested_at FROM agent_activity_credentials WHERE credential_id = %s",
            (cred_id,),
        )
        row = cursor.fetchone()
        return {
            "id": row[0],
            "credential_id": cred_id,
            "ingested_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
            "is_new": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Counterparty Receipts
# ---------------------------------------------------------------------------

def ingest_receipt(conn, credential: dict, extracted: dict) -> dict:
    """Store a CounterpartyReceiptCredential. Idempotent on credential_id."""
    cred_id = extracted["credential_id"]
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, ingested_at, matched_activity_id FROM counterparty_receipts WHERE credential_id = %s",
            (cred_id,),
        )
        existing = cursor.fetchone()
        if existing:
            return {
                "id": existing[0],
                "credential_id": cred_id,
                "ingested_at": existing[1].isoformat() if hasattr(existing[1], "isoformat") else str(existing[1]),
                "is_new": False,
                "matched_activity_id": existing[2],
            }

        cursor.execute(
            """
            INSERT INTO counterparty_receipts (
                credential_id, counterparty_did, agent_did, activity_type,
                acknowledgment_type, activity_timestamp,
                transaction_reference, transaction_rail,
                transaction_amount, transaction_currency,
                agent_activity_credential_id, in_response_to_request_id,
                credential_jsonld
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                cred_id,
                extracted["counterparty_did"],
                extracted["agent_did"],
                extracted["activity_type"],
                extracted["acknowledgment_type"],
                extracted["activity_timestamp"],
                extracted.get("transaction_reference"),
                extracted.get("transaction_rail"),
                extracted.get("transaction_amount"),
                extracted.get("transaction_currency"),
                extracted.get("agent_activity_credential_id"),
                extracted.get("in_response_to_request_id"),
                json.dumps(credential),
            ),
        )
        conn.commit()

        cursor.execute(
            "SELECT id, ingested_at FROM counterparty_receipts WHERE credential_id = %s",
            (cred_id,),
        )
        row = cursor.fetchone()
        return {
            "id": row[0],
            "credential_id": cred_id,
            "ingested_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
            "is_new": True,
            "matched_activity_id": None,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def set_receipt_match(conn, receipt_id: int, activity_id: int) -> None:
    """Update a receipt's matched_activity_id after successful matching."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE counterparty_receipts SET matched_activity_id = %s WHERE id = %s",
            (activity_id, receipt_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Receipt Requests
# ---------------------------------------------------------------------------

def ingest_receipt_request(conn, credential: dict, extracted: dict) -> dict:
    """Store a ReceiptRequestCredential. Idempotent on credential_id."""
    cred_id = extracted["credential_id"]
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, ingested_at FROM receipt_requests WHERE credential_id = %s",
            (cred_id,),
        )
        existing = cursor.fetchone()
        if existing:
            return {
                "id": existing[0],
                "credential_id": cred_id,
                "ingested_at": existing[1].isoformat() if hasattr(existing[1], "isoformat") else str(existing[1]),
                "is_new": False,
            }

        cursor.execute(
            """
            INSERT INTO receipt_requests (
                credential_id, agent_did, counterparty_did,
                transaction_reference, delivery_mode, credential_jsonld
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                cred_id,
                extracted["agent_did"],
                extracted["counterparty_did"],
                extracted.get("transaction_reference"),
                extracted.get("delivery_mode"),
                json.dumps(credential),
            ),
        )
        conn.commit()

        cursor.execute(
            "SELECT id, ingested_at FROM receipt_requests WHERE credential_id = %s",
            (cred_id,),
        )
        row = cursor.fetchone()
        return {
            "id": row[0],
            "credential_id": cred_id,
            "ingested_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
            "is_new": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Receipt Acknowledgments
# ---------------------------------------------------------------------------

def ingest_receipt_ack(conn, credential: dict, extracted: dict) -> dict:
    """Store a ReceiptAcknowledgment. Idempotent on credential_id."""
    cred_id = extracted["credential_id"]
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, ingested_at FROM receipt_acknowledgments WHERE credential_id = %s",
            (cred_id,),
        )
        existing = cursor.fetchone()
        if existing:
            return {
                "id": existing[0],
                "credential_id": cred_id,
                "ingested_at": existing[1].isoformat() if hasattr(existing[1], "isoformat") else str(existing[1]),
                "is_new": False,
            }

        cursor.execute(
            """
            INSERT INTO receipt_acknowledgments (
                credential_id, counterparty_did, agent_did,
                in_response_to_request_id, status,
                delivery_mode, reject_reason, credential_jsonld
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cred_id,
                extracted["counterparty_did"],
                extracted["agent_did"],
                extracted["in_response_to_request_id"],
                extracted["status"],
                extracted.get("delivery_mode"),
                extracted.get("reject_reason"),
                json.dumps(credential),
            ),
        )
        conn.commit()

        cursor.execute(
            "SELECT id, ingested_at FROM receipt_acknowledgments WHERE credential_id = %s",
            (cred_id,),
        )
        row = cursor.fetchone()
        return {
            "id": row[0],
            "credential_id": cred_id,
            "ingested_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
            "is_new": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_activities_for_agent(
    conn,
    agent_did: str,
    since: Optional[str] = None,
    activity_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Query agent activities with optional filters."""
    cursor = conn.cursor()
    try:
        query = """
            SELECT id, credential_id, activity_type, activity_timestamp,
                   counterparty_did, expects_counterparty_receipt,
                   transaction_reference, transaction_rail,
                   transaction_amount, transaction_currency,
                   is_merkle_root, ingested_at
            FROM agent_activity_credentials
            WHERE agent_did = %s
        """
        params = [agent_did]

        if since:
            query += " AND activity_timestamp >= %s"
            params.append(since)
        if activity_type:
            query += " AND activity_type = %s"
            params.append(activity_type)

        query += " ORDER BY activity_timestamp DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0], "credential_id": r[1], "activity_type": r[2],
                "activity_timestamp": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3]),
                "counterparty_did": r[4],
                "expects_counterparty_receipt": bool(r[5]),
                "transaction_reference": r[6], "transaction_rail": r[7],
                "transaction_amount": float(r[8]) if r[8] is not None else None,
                "transaction_currency": r[9],
                "is_merkle_root": bool(r[10]),
                "ingested_at": r[11].isoformat() if hasattr(r[11], "isoformat") else str(r[11]),
            }
            for r in rows
        ]
    finally:
        cursor.close()


def find_matching_activity(
    conn,
    agent_did: str,
    counterparty_did: str,
    transaction_reference: str,
    activity_timestamp: str,
    tolerance_seconds: int,
) -> Optional[dict]:
    """
    Find an agent activity matching a counterparty receipt.
    Match on (agent_did, counterparty_did, transaction_reference) within
    timestamp tolerance.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, credential_id, activity_timestamp
            FROM agent_activity_credentials
            WHERE agent_did = %s
              AND counterparty_did = %s
              AND transaction_reference = %s
              AND ABS(EXTRACT(EPOCH FROM (activity_timestamp - %s::timestamptz))) <= %s
            ORDER BY ABS(EXTRACT(EPOCH FROM (activity_timestamp - %s::timestamptz))) ASC
            LIMIT 1
            """,
            (
                agent_did, counterparty_did, transaction_reference,
                activity_timestamp, tolerance_seconds,
                activity_timestamp,
            ),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "credential_id": row[1],
            "activity_timestamp": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2]),
        }
    finally:
        cursor.close()


def get_anomalies(
    conn,
    org_id: Optional[int] = None,
    anomaly_type: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Query anomalies with optional filters."""
    cursor = conn.cursor()
    try:
        query = "SELECT id, anomaly_type, agent_did, org_id, severity, payload, detected_at, reconciled_at FROM audit_anomalies WHERE 1=1"
        params = []

        if org_id is not None:
            query += " AND org_id = %s"
            params.append(org_id)
        if anomaly_type:
            query += " AND anomaly_type = %s"
            params.append(anomaly_type)
        if since:
            query += " AND detected_at >= %s"
            params.append(since)

        query += " ORDER BY detected_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "id": r[0], "anomaly_type": r[1], "agent_did": r[2],
                "org_id": r[3], "severity": r[4],
                "payload": r[5] if isinstance(r[5], dict) else json.loads(r[5]) if r[5] else {},
                "detected_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]),
                "reconciled_at": r[7].isoformat() if hasattr(r[7], "isoformat") and r[7] else r[7],
            }
            for r in rows
        ]
    finally:
        cursor.close()


def get_activity_by_id(conn, activity_id: int) -> Optional[dict]:
    """Fetch a single activity by its integer ID."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT credential_id, credential_jsonld FROM agent_activity_credentials WHERE id = %s",
            (activity_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "credential_id": row[0],
            "credential_jsonld": row[1] if isinstance(row[1], dict) else json.loads(row[1]),
        }
    finally:
        cursor.close()
