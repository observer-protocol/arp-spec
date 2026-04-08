#!/usr/bin/env python3
"""
DID Resolver — Observer Protocol
Resolves did:web DIDs to DID Documents via HTTPS.
Used by all VC verification flows.
"""

import json
import os
from typing import Optional

import base58
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import HTTPException

# Database configuration
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    """Get PostgreSQL connection"""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def fetch_local_did_document(did: str, did_parts: list) -> tuple:
    """Fetch DID document from local database - supports path-based did:web DIDs."""
    from did_document_builder import build_agent_did_document, build_org_did_document

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Path-based: did:web:observerprotocol.org:agents:{agent_id}
        if len(did_parts) >= 3 and did_parts[1] == "agents":
            agent_id = did_parts[2]
            cursor.execute(
                "SELECT did_document, public_key, agent_did FROM observer_agents WHERE agent_id = %s",
                (agent_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

            # Use stored document if available, otherwise build dynamically
            if row["did_document"]:
                doc = json.loads(row["did_document"]) if isinstance(row["did_document"], str) else row["did_document"]
            elif row["public_key"]:
                doc = build_agent_did_document(agent_id, row["public_key"])
            else:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' has no public key or DID document")

            return doc, {"type": "agent", "source": "local"}

        # Path-based: did:web:observerprotocol.org:orgs:{org_id}
        if len(did_parts) >= 3 and did_parts[1] == "orgs":
            org_id = did_parts[2]
            cursor.execute(
                "SELECT did_document, public_key FROM organizations WHERE org_id = %s",
                (org_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Organization '{org_id}' not found")

            if row["did_document"]:
                doc = json.loads(row["did_document"]) if isinstance(row["did_document"], str) else row["did_document"]
            elif row["public_key"]:
                doc = build_org_did_document(org_id, row["public_key"])
            else:
                raise HTTPException(status_code=404, detail=f"Organization '{org_id}' has no public key or DID document")

            return doc, {"type": "org", "source": "local"}

        # Root DID: did:web:observerprotocol.org
        cursor.execute(
            "SELECT document FROM op_did_document ORDER BY updated_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Root DID document not found")
        doc = json.loads(row["document"]) if isinstance(row["document"], str) else row["document"]
        return doc, {"type": "root", "source": "local"}

    finally:
        cursor.close()
        conn.close()


def resolve_did(did_string: str) -> dict:
    """
    Resolve a DID string to its DID Document.

    Args:
        did_string: The DID to resolve, e.g.
            "did:web:observerprotocol.org:agents:abc123"

    Returns:
        Validated DID Document dict.

    Raises:
        ValueError: If the DID is malformed or uses an unsupported method.
        httpx.HTTPStatusError: If the remote document cannot be fetched.
    """
    if not isinstance(did_string, str) or not did_string.startswith("did:"):
        raise ValueError(f"Not a valid DID string: {did_string!r}")

    parts = did_string.split(":", 2)
    if len(parts) < 3:
        raise ValueError(f"Malformed DID (missing method-specific ID): {did_string!r}")

    method = parts[1]
    if method == "web":
        return resolve_did_web(did_string)

    raise ValueError(
        f"Unsupported DID method: {method!r}. Only did:web is supported."
    )


def resolve_did_web(did: str) -> dict:
    """
    Resolve a did:web DID to its DID Document via HTTPS.

    did:web URL mapping (https://w3c-ccg.github.io/did-method-web/):
      did:web:example.com               → https://example.com/.well-known/did.json
      did:web:example.com:path:segments → https://example.com/path/segments/did.json
    """
    identifier = did[len("did:web:"):]
    parts = identifier.split(":")
    domain = parts[0]
    path_segments = parts[1:] if len(parts) > 1 else []

    if path_segments:
        url = f"https://{domain}/{'/'.join(path_segments)}/did.json"
    else:
        url = f"https://{domain}/.well-known/did.json"

    # Allow local override to avoid loopback through Cloudflare
    local_base = os.environ.get("DID_LOCAL_BASE_URL")
    if local_base and domain == os.environ.get("OP_BASE_DOMAIN", "observerprotocol.org"):
        if path_segments:
            url = f"{local_base}/{'/'.join(path_segments)}/did.json"
        else:
            url = f"{local_base}/.well-known/did.json"

    timeout = float(os.environ.get("DID_RESOLVE_TIMEOUT_SECONDS", "10"))

    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()

    doc = response.json()
    validate_did_document(doc, did)
    return doc


def validate_did_document(doc: dict, expected_did: str) -> None:
    """
    Validate a DID Document for W3C conformance.

    Checks:
    - doc.id matches expected_did
    - At least one verificationMethod is present
    - Every verificationMethod has publicKeyMultibase (base58btc prefix 'z')

    Raises:
        ValueError: On any conformance failure.
    """
    if not isinstance(doc, dict):
        raise ValueError("DID Document must be a JSON object")

    if doc.get("id") != expected_did:
        raise ValueError(
            f"DID Document 'id' mismatch: expected {expected_did!r}, "
            f"got {doc.get('id')!r}"
        )

    methods = doc.get("verificationMethod")
    if not isinstance(methods, list) or len(methods) == 0:
        raise ValueError(
            "DID Document must have at least one verificationMethod"
        )

    for vm in methods:
        key = vm.get("publicKeyMultibase")
        if not isinstance(key, str) or not key.startswith("z"):
            raise ValueError(
                f"verificationMethod {vm.get('id')!r} is missing a valid "
                f"publicKeyMultibase (must be base58btc, prefix 'z')"
            )


def extract_public_key_bytes(
    did_document: dict,
    key_id: Optional[str] = None,
) -> bytes:
    """
    Extract the Ed25519 public key bytes from a DID Document.

    Args:
        did_document: A validated DID Document dict.
        key_id: The specific verificationMethod id to use.
                If None, the first method is used.

    Returns:
        Raw public key bytes.

    Raises:
        ValueError: If the key is not found or cannot be decoded.
    """
    methods = did_document.get("verificationMethod", [])
    if not methods:
        raise ValueError("No verificationMethod in DID Document")

    if key_id:
        vm = next((m for m in methods if m.get("id") == key_id), None)
        if vm is None:
            raise ValueError(
                f"Key ID {key_id!r} not found in DID Document"
            )
    else:
        vm = methods[0]

    multibase = vm.get("publicKeyMultibase", "")
    if not multibase.startswith("z"):
        raise ValueError(
            "publicKeyMultibase must use base58btc encoding (prefix 'z')"
        )

    return base58.b58decode(multibase[1:])


def extract_public_key_hex(
    did_document: dict,
    key_id: Optional[str] = None,
) -> str:
    """
    Extract the Ed25519 public key from a DID Document as a hex string.
    """
    return extract_public_key_bytes(did_document, key_id).hex()
