"""
Data access layer for OP-hosted status lists (vac_revocation_registry).

Handles CRUD operations on the vac_revocation_registry table, which stores
Tier 3 (OP-hosted) Bitstring Status List state. Each row represents one
status list owned by one DID, tracking a single statusPurpose.

This module does not import FastAPI or handle HTTP concerns. It takes a
database connection and returns plain dicts or raises exceptions.

Table schema (migration 006):
    id                        SERIAL PRIMARY KEY
    status_list_id            TEXT UNIQUE NOT NULL
    status_list_url           TEXT UNIQUE NOT NULL
    owner_did                 TEXT NOT NULL
    status_purpose            TEXT NOT NULL          -- 'revocation' | 'suspension'
    current_bitstring         TEXT NOT NULL           -- gzip+base64url encoded
    current_credential_jsonld JSONB NOT NULL          -- full signed BitstringStatusListCredential
    next_available_index      INTEGER NOT NULL DEFAULT 0
    total_capacity            INTEGER NOT NULL DEFAULT 131072
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
    last_updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from bitstring_status_list import (
    create_bitstring,
    encode_bitstring,
    DEFAULT_BITSTRING_SIZE,
)


class StatusListNotFoundError(Exception):
    pass


class StatusListCapacityExhaustedError(Exception):
    pass


class StatusListOwnerMismatchError(Exception):
    pass


def generate_list_id() -> str:
    """Generate a unique status list ID."""
    return f"sl-{uuid.uuid4().hex[:12]}"


def create_status_list(
    conn,
    owner_did: str,
    status_purpose: str,
    base_url: str,
    total_capacity: int = DEFAULT_BITSTRING_SIZE,
) -> dict:
    """
    Allocate a new status list for an issuer.

    Creates a zeroed bitstring, stores it, and returns the list metadata.
    The initial current_credential_jsonld is a placeholder — the issuer must
    submit a signed BitstringStatusListCredential via the update endpoint
    before the list is publicly serveable.

    Args:
        conn: psycopg2 connection.
        owner_did: The DID that owns this status list.
        status_purpose: 'revocation' or 'suspension'.
        base_url: Base URL for constructing the status list URL
                  (e.g., "https://api.observerprotocol.org").
        total_capacity: Bitstring size in bits (default 131,072).

    Returns:
        Dict with list_id, status_list_url, status_purpose, total_capacity.
    """
    if status_purpose not in ("revocation", "suspension"):
        raise ValueError(f"status_purpose must be 'revocation' or 'suspension', got: {status_purpose!r}")

    list_id = generate_list_id()
    status_list_url = f"{base_url}/sovereign/status-lists/{list_id}"

    raw = create_bitstring(total_capacity)
    encoded = encode_bitstring(raw)

    # Placeholder credential — not valid until the issuer signs and submits
    placeholder_credential = {
        "@context": ["https://www.w3.org/ns/credentials/v2"],
        "type": ["VerifiableCredential", "BitstringStatusListCredential"],
        "issuer": owner_did,
        "credentialSubject": {
            "type": "BitstringStatusList",
            "statusPurpose": status_purpose,
            "encodedList": encoded,
        },
        "_placeholder": True,
    }

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO vac_revocation_registry
                (status_list_id, status_list_url, owner_did, status_purpose,
                 current_bitstring, current_credential_jsonld,
                 next_available_index, total_capacity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                list_id,
                status_list_url,
                owner_did,
                status_purpose,
                encoded,
                json.dumps(placeholder_credential),
                0,
                total_capacity,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()

    return {
        "listId": list_id,
        "statusListUrl": status_list_url,
        "statusPurpose": status_purpose,
        "totalCapacity": total_capacity,
    }


def get_status_list(conn, list_id: str) -> Optional[dict]:
    """
    Fetch a status list by its ID.

    Returns:
        Dict with all columns, or None if not found.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT status_list_id, status_list_url, owner_did, status_purpose,
                   current_bitstring, current_credential_jsonld,
                   next_available_index, total_capacity,
                   created_at, last_updated_at
            FROM vac_revocation_registry
            WHERE status_list_id = %s
            """,
            (list_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "status_list_id": row[0],
            "status_list_url": row[1],
            "owner_did": row[2],
            "status_purpose": row[3],
            "current_bitstring": row[4],
            "current_credential_jsonld": row[5] if isinstance(row[5], dict) else json.loads(row[5]),
            "next_available_index": row[6],
            "total_capacity": row[7],
            "created_at": row[8],
            "last_updated_at": row[9],
        }
    finally:
        cursor.close()


def get_status_list_credential(conn, list_id: str) -> Optional[dict]:
    """
    Fetch only the current signed BitstringStatusListCredential for a list.
    This is what the public GET endpoint returns.

    Returns:
        The credential dict, or None if not found.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT current_credential_jsonld
            FROM vac_revocation_registry
            WHERE status_list_id = %s
            """,
            (list_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        cred = row[0]
        if isinstance(cred, str):
            cred = json.loads(cred)

        # Don't serve placeholder credentials
        if cred.get("_placeholder"):
            return None

        return cred
    finally:
        cursor.close()


def allocate_index(conn, list_id: str, owner_did: str) -> dict:
    """
    Atomically allocate the next available index on a status list.

    Args:
        conn: psycopg2 connection.
        list_id: The status list ID.
        owner_did: The DID requesting allocation (must match list owner).

    Returns:
        Dict with listId, allocatedIndex, remainingCapacity.

    Raises:
        StatusListNotFoundError: If list_id doesn't exist.
        StatusListOwnerMismatchError: If owner_did doesn't match.
        StatusListCapacityExhaustedError: If the list is full.
    """
    cursor = conn.cursor()
    try:
        # SELECT FOR UPDATE to serialize concurrent allocations
        cursor.execute(
            """
            SELECT owner_did, next_available_index, total_capacity
            FROM vac_revocation_registry
            WHERE status_list_id = %s
            FOR UPDATE
            """,
            (list_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise StatusListNotFoundError(f"Status list {list_id!r} not found")

        db_owner, next_idx, capacity = row

        if db_owner != owner_did:
            raise StatusListOwnerMismatchError(
                f"DID {owner_did!r} is not the owner of status list {list_id!r}"
            )

        if next_idx >= capacity:
            raise StatusListCapacityExhaustedError(
                f"Status list {list_id!r} is full ({capacity} indices allocated)"
            )

        # Increment atomically
        cursor.execute(
            """
            UPDATE vac_revocation_registry
            SET next_available_index = next_available_index + 1
            WHERE status_list_id = %s
            """,
            (list_id,),
        )
        conn.commit()

        return {
            "listId": list_id,
            "allocatedIndex": next_idx,
            "remainingCapacity": capacity - next_idx - 1,
        }
    except (StatusListNotFoundError, StatusListOwnerMismatchError, StatusListCapacityExhaustedError):
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def update_status_list(
    conn,
    list_id: str,
    new_credential: dict,
    new_bitstring_encoded: str,
) -> dict:
    """
    Replace the current status list credential and bitstring.

    Authority and validity checks are performed by the caller (API layer)
    before calling this function.

    Args:
        conn: psycopg2 connection.
        list_id: The status list ID.
        new_credential: The full signed BitstringStatusListCredential dict.
        new_bitstring_encoded: The new encoded bitstring (from the credential).

    Returns:
        Dict with listId, updated status.

    Raises:
        StatusListNotFoundError: If list_id doesn't exist.
    """
    cursor = conn.cursor()
    try:
        # Check existence first (compatible with both PostgreSQL and SQLite)
        cursor.execute(
            "SELECT 1 FROM vac_revocation_registry WHERE status_list_id = %s",
            (list_id,),
        )
        if not cursor.fetchone():
            raise StatusListNotFoundError(f"Status list {list_id!r} not found")

        cursor.execute(
            """
            UPDATE vac_revocation_registry
            SET current_credential_jsonld = %s,
                current_bitstring = %s,
                last_updated_at = NOW()
            WHERE status_list_id = %s
            """,
            (
                json.dumps(new_credential),
                new_bitstring_encoded,
                list_id,
            ),
        )
        conn.commit()
        return {"listId": list_id, "updated": True}

    except StatusListNotFoundError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def get_lists_by_owner(conn, owner_did: str) -> list[dict]:
    """
    Fetch all status lists owned by a given DID.

    Returns:
        List of dicts with list metadata.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT status_list_id, status_list_url, status_purpose,
                   next_available_index, total_capacity, created_at, last_updated_at
            FROM vac_revocation_registry
            WHERE owner_did = %s
            ORDER BY created_at
            """,
            (owner_did,),
        )
        rows = cursor.fetchall()
        return [
            {
                "status_list_id": r[0],
                "status_list_url": r[1],
                "status_purpose": r[2],
                "next_available_index": r[3],
                "total_capacity": r[4],
                "created_at": r[5],
                "last_updated_at": r[6],
            }
            for r in rows
        ]
    finally:
        cursor.close()
