"""
Anomaly detection for Spec 3.4 audit trails.

Two priority anomaly classes implemented this pass:

  UnmatchedReceiptAnomaly — a counterparty receipt arrives but no corresponding
    agent activity exists. Strong signal: counterparty says a transaction happened
    but the agent never logged it.

  ReceiptRejectedAnomaly — a ReceiptAcknowledgment arrives with status "rejected".
    Counterparty denies the transaction the agent claimed.

Deferred:
  CoverageGap — agent activity expects receipt but window elapsed without match.
  ReceiptDeliveryTimeout — acknowledgment pending but receipt never arrived.
"""

import json
from typing import Optional


def record_anomaly(
    conn,
    anomaly_type: str,
    agent_did: str,
    severity: str,
    payload: dict,
    org_id: Optional[int] = None,
) -> int:
    """
    Record an anomaly in the audit_anomalies table.

    Returns:
        The anomaly's integer ID.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO audit_anomalies (anomaly_type, agent_did, org_id, severity, payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (anomaly_type, agent_did, org_id, severity, json.dumps(payload)),
        )
        conn.commit()
        # Fetch the inserted row's ID (compatible with both PostgreSQL and SQLite)
        cursor.execute(
            "SELECT id FROM audit_anomalies WHERE anomaly_type = %s AND agent_did = %s ORDER BY detected_at DESC LIMIT 1",
            (anomaly_type, agent_did),
        )
        anomaly_id = cursor.fetchone()[0]
        return anomaly_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def detect_unmatched_receipt(
    conn,
    receipt_id: int,
    receipt_extracted: dict,
    matched_activity_id: Optional[int],
) -> Optional[int]:
    """
    If a receipt has no matching activity, record an UnmatchedReceiptAnomaly.

    Called after match_and_link returns None.

    Returns:
        Anomaly ID if recorded, None if not applicable.
    """
    if matched_activity_id is not None:
        return None

    # Only flag if there's a transaction reference — receipts without one
    # can't be meaningfully matched
    if not receipt_extracted.get("transaction_reference"):
        return None

    return record_anomaly(
        conn=conn,
        anomaly_type="UnmatchedReceiptAnomaly",
        agent_did=receipt_extracted["agent_did"],
        severity="high",
        payload={
            "receipt_id": receipt_id,
            "receipt_credential_id": receipt_extracted["credential_id"],
            "counterparty_did": receipt_extracted["counterparty_did"],
            "transaction_reference": receipt_extracted.get("transaction_reference"),
            "activity_type": receipt_extracted.get("activity_type"),
            "activity_timestamp": receipt_extracted.get("activity_timestamp"),
            "description": (
                f"Counterparty {receipt_extracted['counterparty_did']} signed a receipt "
                f"for transaction {receipt_extracted.get('transaction_reference')} "
                f"but no corresponding AgentActivityCredential exists from "
                f"{receipt_extracted['agent_did']}."
            ),
        },
    )


def detect_receipt_rejected(
    conn,
    ack_extracted: dict,
) -> Optional[int]:
    """
    If a ReceiptAcknowledgment has status "rejected", record a
    ReceiptRejectedAnomaly.

    Called during receipt-ack ingest.

    Returns:
        Anomaly ID if recorded, None if not applicable.
    """
    if ack_extracted.get("status") != "rejected":
        return None

    return record_anomaly(
        conn=conn,
        anomaly_type="ReceiptRejectedAnomaly",
        agent_did=ack_extracted["agent_did"],
        severity="high",
        payload={
            "ack_credential_id": ack_extracted["credential_id"],
            "counterparty_did": ack_extracted["counterparty_did"],
            "in_response_to_request_id": ack_extracted.get("in_response_to_request_id"),
            "reject_reason": ack_extracted.get("reject_reason"),
            "description": (
                f"Counterparty {ack_extracted['counterparty_did']} rejected receipt request "
                f"{ack_extracted.get('in_response_to_request_id')}: "
                f"{ack_extracted.get('reject_reason', 'no reason given')}."
            ),
        },
    )
