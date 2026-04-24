"""
Extract indexed fields from audit credential types for storage.

Each extractor takes a full signed VC dict and returns a flat dict
of the fields needed by audit_store's ingest functions.
"""

from typing import Optional


def extract_activity_fields(credential: dict) -> dict:
    """Extract indexed fields from an AgentActivityCredential."""
    subject = credential.get("credentialSubject", {})
    tx = subject.get("transactionDetails", {})
    merkle = subject.get("merkleProof", {})
    amount = tx.get("amount", {})

    types = credential.get("type", [])
    is_merkle_root = "AgentActivityMerkleRoot" in types

    return {
        "credential_id": credential.get("id"),
        "agent_did": credential.get("issuer"),
        "activity_type": subject.get("activityType"),
        "activity_timestamp": subject.get("activityTimestamp") or subject.get("windowStart") or credential.get("validFrom"),
        "is_merkle_root": is_merkle_root,
        "merkle_root_hash": subject.get("merkleRoot") if is_merkle_root else None,
        "parent_root_credential_id": merkle.get("rootCredentialId"),
        "counterparty_did": subject.get("counterpartyDid"),
        "expects_counterparty_receipt": subject.get("expectsCounterpartyReceipt", False),
        "expected_receipt_window": subject.get("expectedReceiptWindow"),
        "transaction_rail": tx.get("rail"),
        "transaction_reference": tx.get("referenceId"),
        "transaction_amount": amount.get("value") if amount else None,
        "transaction_currency": amount.get("currency") if amount else None,
        "delegation_credential_id": subject.get("delegationCredentialId"),
    }


def extract_receipt_fields(credential: dict) -> dict:
    """Extract indexed fields from a CounterpartyReceiptCredential."""
    subject = credential.get("credentialSubject", {})
    tx = subject.get("transactionDetails", {})
    amount = tx.get("amount", {})

    return {
        "credential_id": credential.get("id"),
        "counterparty_did": credential.get("issuer"),
        "agent_did": subject.get("id"),
        "activity_type": subject.get("activityType"),
        "acknowledgment_type": subject.get("acknowledgmentType"),
        "activity_timestamp": subject.get("activityTimestamp") or credential.get("validFrom"),
        "transaction_reference": tx.get("referenceId"),
        "transaction_rail": tx.get("rail"),
        "transaction_amount": amount.get("value") if amount else None,
        "transaction_currency": amount.get("currency") if amount else None,
        "agent_activity_credential_id": subject.get("agentActivityCredentialId"),
        "in_response_to_request_id": subject.get("inResponseToRequestId"),
    }


def extract_receipt_request_fields(credential: dict) -> dict:
    """Extract indexed fields from a ReceiptRequestCredential."""
    subject = credential.get("credentialSubject", {})
    tx = subject.get("transactionDetails", {})
    delivery = subject.get("deliveryChannel", {})

    return {
        "credential_id": credential.get("id"),
        "agent_did": credential.get("issuer"),
        "counterparty_did": subject.get("id"),
        "transaction_reference": tx.get("referenceId"),
        "delivery_mode": delivery.get("mode"),
    }


def extract_receipt_ack_fields(credential: dict) -> dict:
    """Extract indexed fields from a ReceiptAcknowledgment."""
    subject = credential.get("credentialSubject", {})

    return {
        "credential_id": credential.get("id"),
        "counterparty_did": credential.get("issuer"),
        "agent_did": subject.get("id"),
        "in_response_to_request_id": subject.get("inResponseToRequestId"),
        "status": subject.get("status"),
        "delivery_mode": subject.get("deliveryMode"),
        "reject_reason": subject.get("rejectReason"),
    }
