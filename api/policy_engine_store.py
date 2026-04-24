"""
Data access layer for policy engine registration and consultation log.

OP-side tables:
  policy_engines          — one engine per org
  policy_consultation_log — audit trail of every consultation call
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional


def register_engine(
    conn,
    org_id: int,
    engine_url: str,
    engine_public_key_did: str,
    engine_name: str,
    engine_version: Optional[str] = None,
    registered_by: Optional[str] = None,
) -> dict:
    """Register or re-register a policy engine for an org. Upsert."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT org_id FROM policy_engines WHERE org_id = %s",
            (org_id,),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE policy_engines SET
                    engine_url = %s, engine_public_key_did = %s,
                    engine_name = %s, engine_version = %s,
                    registered_at = NOW(), registered_by = %s, is_active = TRUE
                WHERE org_id = %s
                """,
                (engine_url, engine_public_key_did, engine_name,
                 engine_version, registered_by, org_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO policy_engines
                    (org_id, engine_url, engine_public_key_did, engine_name,
                     engine_version, registered_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (org_id, engine_url, engine_public_key_did, engine_name,
                 engine_version, registered_by),
            )

        conn.commit()
        return get_engine(conn, org_id)

    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def get_engine(conn, org_id: int) -> Optional[dict]:
    """Get the registered engine for an org."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT org_id, engine_url, engine_public_key_did, engine_name,
                   engine_version, registered_at, is_active
            FROM policy_engines
            WHERE org_id = %s AND is_active = TRUE
            """,
            (org_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "org_id": row[0],
            "engine_url": row[1],
            "engine_public_key_did": row[2],
            "engine_name": row[3],
            "engine_version": row[4],
            "registered_at": row[5].isoformat() if hasattr(row[5], "isoformat") else str(row[5]),
            "is_active": row[6],
        }
    finally:
        cursor.close()


def deactivate_engine(conn, org_id: int) -> bool:
    """Soft-delete: set is_active = FALSE. Returns to permit-by-default."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE policy_engines SET is_active = FALSE WHERE org_id = %s AND is_active = TRUE",
            (org_id,),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def log_consultation(
    conn,
    org_id: int,
    engine_url: str,
    request_id: str,
    action_type: str,
    decision: str,
    decision_payload: dict,
    policy_id: Optional[str] = None,
    engine_signature: Optional[str] = None,
    eval_duration_ms: Optional[int] = None,
) -> int:
    """Write a consultation log entry. Returns the log entry ID."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO policy_consultation_log
                (org_id, engine_url, request_id, action_type, decision,
                 policy_id, decision_payload, engine_signature, eval_duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (org_id, engine_url, request_id, action_type, decision,
             policy_id, json.dumps(decision_payload), engine_signature,
             eval_duration_ms),
        )
        conn.commit()
        # Get the inserted ID
        cursor.execute(
            "SELECT id FROM policy_consultation_log WHERE request_id = %s ORDER BY created_at DESC LIMIT 1",
            (request_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def get_consultations(
    conn,
    org_id: int,
    limit: int = 50,
) -> list[dict]:
    """Query recent consultation log entries for an org."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, request_id, action_type, decision, policy_id,
                   decision_payload, eval_duration_ms, created_at
            FROM policy_consultation_log
            WHERE org_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (org_id, limit),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "request_id": str(r[1]),
                "action_type": r[2],
                "decision": r[3],
                "policy_id": r[4],
                "decision_payload": r[5] if isinstance(r[5], dict) else json.loads(r[5]) if r[5] else {},
                "eval_duration_ms": r[6],
                "created_at": r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7]),
            }
            for r in rows
        ]
    finally:
        cursor.close()


def get_consultation_by_request_id(conn, request_id: str) -> Optional[dict]:
    """Get a specific consultation by request_id."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, org_id, engine_url, request_id, action_type, decision,
                   policy_id, decision_payload, engine_signature, eval_duration_ms, created_at
            FROM policy_consultation_log
            WHERE request_id = %s
            """,
            (request_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "org_id": row[1], "engine_url": row[2],
            "request_id": str(row[3]), "action_type": row[4], "decision": row[5],
            "policy_id": row[6],
            "decision_payload": row[7] if isinstance(row[7], dict) else json.loads(row[7]) if row[7] else {},
            "engine_signature": row[8], "eval_duration_ms": row[9],
            "created_at": row[10].isoformat() if hasattr(row[10], "isoformat") else str(row[10]),
        }
    finally:
        cursor.close()
