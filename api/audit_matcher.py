"""
Match logic for pairing agent activities with counterparty receipts.

Matching joins on (agent_did, counterparty_did, transaction_reference)
within a rail-aware timestamp tolerance per Spec 3.4 §7.2 / §14.2.

Called synchronously on receipt ingest. When a match is found, the
receipt's matched_activity_id is set and anomaly detection is skipped
for that pair. When no match is found, an UnmatchedReceiptAnomaly is
recorded.
"""

from typing import Optional

from audit_store import find_matching_activity, set_receipt_match


# Rail finality times in seconds. Tolerance = max(120, 5 * finality).
# TODO: Move to Type Registry or config when more rails are added.
RAIL_FINALITY_SECONDS = {
    "trc20": 3,
    "tron": 3,
    "lightning": 1,
    "solana": 2.5,
}

DEFAULT_TOLERANCE_SECONDS = 120  # 2-minute floor


def get_match_tolerance(rail: Optional[str]) -> int:
    """
    Compute clock-skew tolerance for a given rail.
    Formula: max(120s, 5 × rail_finality_time).
    """
    if rail and rail in RAIL_FINALITY_SECONDS:
        rail_tolerance = int(5 * RAIL_FINALITY_SECONDS[rail])
        return max(DEFAULT_TOLERANCE_SECONDS, rail_tolerance)
    return DEFAULT_TOLERANCE_SECONDS


def attempt_match(conn, receipt_extracted: dict) -> Optional[dict]:
    """
    Attempt to match a newly ingested counterparty receipt to an
    existing agent activity.

    Args:
        conn: Database connection.
        receipt_extracted: Extracted fields from the receipt, including:
            agent_did, counterparty_did, transaction_reference,
            activity_timestamp, transaction_rail

    Returns:
        The matched activity dict if found, None otherwise.
    """
    agent_did = receipt_extracted.get("agent_did")
    counterparty_did = receipt_extracted.get("counterparty_did")
    tx_ref = receipt_extracted.get("transaction_reference")

    if not all([agent_did, counterparty_did, tx_ref]):
        return None

    tolerance = get_match_tolerance(receipt_extracted.get("transaction_rail"))

    return find_matching_activity(
        conn=conn,
        agent_did=agent_did,
        counterparty_did=counterparty_did,
        transaction_reference=tx_ref,
        activity_timestamp=receipt_extracted["activity_timestamp"],
        tolerance_seconds=tolerance,
    )


def match_and_link(conn, receipt_id: int, receipt_extracted: dict) -> Optional[int]:
    """
    Attempt match and, if found, update the receipt's matched_activity_id.

    Returns:
        The matched activity's integer ID, or None if no match.
    """
    matched = attempt_match(conn, receipt_extracted)
    if matched:
        set_receipt_match(conn, receipt_id, matched["id"])
        return matched["id"]
    return None
