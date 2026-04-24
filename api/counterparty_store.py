"""
Data access layer for counterparties table.

Spec 3.6 — Counterparty Management (Lightweight).
Org-scoped relationship registry: observed → accepted → revoked lifecycle.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional


TRUST_SCORE_TTL_MINUTES = 10


def list_counterparties(
    conn,
    org_id: int,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List counterparties for an org with optional status filter."""
    cursor = conn.cursor()
    try:
        where = "WHERE org_id = %s"
        params = [org_id]
        if status:
            where += " AND status = %s"
            params.append(status)

        cursor.execute(f"SELECT COUNT(*) FROM counterparties {where}", params)
        total = cursor.fetchone()[0]

        cursor.execute(
            f"""SELECT id, counterparty_did, status, tag, first_seen_at,
                       last_transacted_at, transaction_count,
                       trust_score_cache, trust_score_cached_at
                FROM counterparties {where}
                ORDER BY last_transacted_at DESC NULLS LAST
                LIMIT %s OFFSET %s""",
            params + [limit, offset],
        )
        rows = cursor.fetchall()
        items = [
            {
                "id": r[0],
                "counterparty_did": r[1],
                "status": r[2],
                "tag": r[3],
                "first_seen_at": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]) if r[4] else None,
                "last_transacted_at": r[5].isoformat() if hasattr(r[5], "isoformat") else str(r[5]) if r[5] else None,
                "transaction_count": r[6],
                "trust_score": r[7],
                "trust_score_as_of": r[8].isoformat() if hasattr(r[8], "isoformat") else str(r[8]) if r[8] else None,
            }
            for r in rows
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        cursor.close()


def get_counterparty(conn, counterparty_id: int, org_id: int) -> Optional[dict]:
    """Get a single counterparty by ID, scoped to org."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT id, org_id, counterparty_did, status, tag, notes,
                      first_seen_at, last_transacted_at, transaction_count,
                      accepted_at, accepted_by, revoked_at, revoked_by, revoke_reason,
                      trust_score_cache, trust_score_cached_at
               FROM counterparties
               WHERE id = %s AND org_id = %s""",
            (counterparty_id, org_id),
        )
        r = cursor.fetchone()
        if not r:
            return None
        return {
            "id": r[0], "org_id": r[1], "counterparty_did": r[2],
            "status": r[3], "tag": r[4], "notes": r[5],
            "first_seen_at": r[6].isoformat() if hasattr(r[6], "isoformat") else str(r[6]) if r[6] else None,
            "last_transacted_at": r[7].isoformat() if hasattr(r[7], "isoformat") else str(r[7]) if r[7] else None,
            "transaction_count": r[8],
            "accepted_at": r[9].isoformat() if hasattr(r[9], "isoformat") else str(r[9]) if r[9] else None,
            "accepted_by": str(r[10]) if r[10] else None,
            "revoked_at": r[11].isoformat() if hasattr(r[11], "isoformat") else str(r[11]) if r[11] else None,
            "revoked_by": str(r[12]) if r[12] else None,
            "revoke_reason": r[13],
            "trust_score": r[14],
            "trust_score_as_of": r[15].isoformat() if hasattr(r[15], "isoformat") else str(r[15]) if r[15] else None,
        }
    finally:
        cursor.close()


def accept_counterparty(
    conn, org_id: int, counterparty_did: str, user_id: str,
    tag: Optional[str] = None, notes: Optional[str] = None,
) -> dict:
    """Accept a counterparty. Creates row if not exists."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM counterparties WHERE org_id = %s AND counterparty_did = %s",
            (org_id, counterparty_did),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """UPDATE counterparties SET
                    status = 'accepted', accepted_at = NOW(), accepted_by = %s,
                    tag = COALESCE(%s, tag), notes = COALESCE(%s, notes),
                    updated_at = NOW()
                WHERE id = %s""",
                (user_id, tag, notes, existing[0]),
            )
            cp_id = existing[0]
        else:
            cursor.execute(
                """INSERT INTO counterparties
                    (org_id, counterparty_did, status, tag, notes,
                     first_seen_at, accepted_at, accepted_by)
                VALUES (%s, %s, 'accepted', %s, %s, NOW(), NOW(), %s)""",
                (org_id, counterparty_did, tag, notes, user_id),
            )
            cursor.execute(
                "SELECT id FROM counterparties WHERE org_id = %s AND counterparty_did = %s",
                (org_id, counterparty_did),
            )
            cp_id = cursor.fetchone()[0]

        conn.commit()
        return get_counterparty(conn, cp_id, org_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def revoke_counterparty(
    conn, counterparty_id: int, org_id: int, user_id: str, reason: Optional[str] = None,
) -> Optional[dict]:
    """Revoke acceptance. Forward-looking only."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE counterparties SET
                status = 'revoked', revoked_at = NOW(), revoked_by = %s,
                revoke_reason = %s, updated_at = NOW()
            WHERE id = %s AND org_id = %s""",
            (user_id, reason, counterparty_id, org_id),
        )
        if cursor.rowcount == 0:
            return None
        conn.commit()
        return get_counterparty(conn, counterparty_id, org_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def update_counterparty_metadata(
    conn, counterparty_id: int, org_id: int,
    tag: Optional[str] = None, notes: Optional[str] = None,
) -> Optional[dict]:
    """Update tag/notes only. Does not change status."""
    cursor = conn.cursor()
    try:
        sets = []
        params = []
        if tag is not None:
            sets.append("tag = %s")
            params.append(tag)
        if notes is not None:
            sets.append("notes = %s")
            params.append(notes)
        if not sets:
            return get_counterparty(conn, counterparty_id, org_id)

        sets.append("updated_at = NOW()")
        params.extend([counterparty_id, org_id])

        cursor.execute(
            f"UPDATE counterparties SET {', '.join(sets)} WHERE id = %s AND org_id = %s",
            params,
        )
        if cursor.rowcount == 0:
            return None
        conn.commit()
        return get_counterparty(conn, counterparty_id, org_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def get_counterparty_status_for_policy(conn, org_id: int, counterparty_did: str) -> dict:
    """Get counterparty status for policy consultation context enrichment."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT status FROM counterparties WHERE org_id = %s AND counterparty_did = %s",
            (org_id, counterparty_did),
        )
        row = cursor.fetchone()
        if not row:
            return {"counterparty_status": "unknown", "accepted_by_org": False}
        return {
            "counterparty_status": row[0],
            "accepted_by_org": row[0] == "accepted",
        }
    finally:
        cursor.close()
