"""
Coverage rollup computation for Spec 3.4.

Computes receipt_coverage_rate for an agent across rolling windows
(7, 30, 90 days). Stores results in audit_coverage_rollup table
for fast query.

coverage_rate = received_receipts / expected_receipts
  - expected = count of activities with expects_counterparty_receipt=true
  - received = count of those that have a matched counterparty receipt
  - null if expected is 0 (no penalty for agents with no counterparty interactions)
"""

from typing import Optional


def compute_coverage(conn, agent_did: str, window_days: int) -> dict:
    """
    Compute and store coverage for an agent over a given window.

    Args:
        conn: Database connection.
        agent_did: The agent's DID.
        window_days: Rolling window size (7, 30, or 90).

    Returns:
        {"agent_did": str, "window_days": int, "expected_receipts": int,
         "received_receipts": int, "coverage_rate": float|None}
    """
    cursor = conn.cursor()
    try:
        # Count expected receipts in window
        cursor.execute(
            """
            SELECT COUNT(*) FROM agent_activity_credentials
            WHERE agent_did = %s
              AND expects_counterparty_receipt = TRUE
              AND activity_timestamp >= NOW() - (%s || ' days')::interval
            """,
            (agent_did, str(window_days)),
        )
        expected = cursor.fetchone()[0]

        # Count matched receipts (activities that have a corresponding receipt)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT a.id)
            FROM agent_activity_credentials a
            JOIN counterparty_receipts r ON r.matched_activity_id = a.id
            WHERE a.agent_did = %s
              AND a.expects_counterparty_receipt = TRUE
              AND a.activity_timestamp >= NOW() - (%s || ' days')::interval
            """,
            (agent_did, str(window_days)),
        )
        received = cursor.fetchone()[0]

        coverage_rate = received / expected if expected > 0 else None

        # Upsert into rollup table
        cursor.execute(
            """
            INSERT INTO audit_coverage_rollup
                (agent_did, window_days, expected_receipts, received_receipts, coverage_rate, computed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (agent_did, window_days) DO UPDATE SET
                expected_receipts = EXCLUDED.expected_receipts,
                received_receipts = EXCLUDED.received_receipts,
                coverage_rate = EXCLUDED.coverage_rate,
                computed_at = NOW()
            """,
            (agent_did, window_days, expected, received, coverage_rate),
        )
        conn.commit()

        return {
            "agent_did": agent_did,
            "window_days": window_days,
            "expected_receipts": expected,
            "received_receipts": received,
            "coverage_rate": float(coverage_rate) if coverage_rate is not None else None,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def get_coverage(conn, agent_did: str, window_days: int = 30) -> Optional[dict]:
    """
    Read precomputed coverage from rollup table.

    Returns:
        Coverage dict or None if not yet computed.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT expected_receipts, received_receipts, coverage_rate, computed_at
            FROM audit_coverage_rollup
            WHERE agent_did = %s AND window_days = %s
            """,
            (agent_did, window_days),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "agent_did": agent_did,
            "window_days": window_days,
            "expected_receipts": row[0],
            "received_receipts": row[1],
            "coverage_rate": float(row[2]) if row[2] is not None else None,
            "computed_at": row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3]),
        }
    finally:
        cursor.close()


def compute_all_windows(conn, agent_did: str) -> list[dict]:
    """Compute coverage for all standard windows (7, 30, 90 days)."""
    return [compute_coverage(conn, agent_did, w) for w in (7, 30, 90)]
