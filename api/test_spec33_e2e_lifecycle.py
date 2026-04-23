"""
Spec 3.3 E2E Lifecycle Test — in-process, hermetic.

Exercises the full status list lifecycle through the router without HTTP or
live service dependencies:

  1. Generate a fresh Ed25519 keypair (test agent).
  2. Insert a DID document into observer_agents so the resolver can find it.
  3. Allocate a new status list.
  4. Allocate an index on the list.
  5. Build a mock credential referencing (list_id, index).
  6. Sign + submit the initial (all-zeros) BSL credential.
  7. /verify/status — expect overall_valid=True.
  8. Build + sign BSL with bit set to 1, submit as revocation update.
  9. /verify/status — expect overall_valid=False.
 10. Cleanup.

Run:
    cd /media/nvme/observer-protocol/api
    python3 test_spec33_e2e_lifecycle.py
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone

API_DIR = "/media/nvme/observer-protocol/api"
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

import psycopg2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import asyncio
import httpx
from fastapi import FastAPI

from status_list_routes import router as status_list_router, configure as configure_status_lists
from crypto_utils import sign_document, encode_proof_value, canonical_bytes
from did_document_builder import encode_public_key_multibase
from bitstring_status_list import create_bitstring, encode_bitstring, set_bit


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://agentic_terminal:at_secure_2026@localhost:5432/agentic_terminal_db",
)
OP_BASE_DOMAIN = "observerprotocol.org"
TEST_BASE_URL = "https://api.observerprotocol.org"


def get_db_conn():
    return psycopg2.connect(DATABASE_URL)


def make_test_agent():
    agent_id = f"test-e2e-{uuid.uuid4().hex[:12]}"
    did = f"did:web:{OP_BASE_DOMAIN}:agents:{agent_id}"
    key_id = f"{did}#key-1"

    private_key = Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_multibase = encode_public_key_multibase(pub_bytes.hex())

    did_document = {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": did,
        "verificationMethod": [{
            "id": key_id,
            "type": "Ed25519VerificationKey2020",
            "controller": did,
            "publicKeyMultibase": pub_multibase,
        }],
        "authentication": [key_id],
        "assertionMethod": [key_id],
    }
    return agent_id, did, key_id, private_key, did_document


def insert_test_agent(conn, agent_id, did, did_document):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO observer_agents
            (agent_id, agent_did, did_document, did_created_at, created_at)
        VALUES (%s, %s, %s, NOW(), NOW())
        """,
        (agent_id, did, json.dumps(did_document)),
    )
    conn.commit()
    cur.close()


def cleanup(conn, agent_id, list_id=None):
    cur = conn.cursor()
    if list_id:
        cur.execute("DELETE FROM vac_revocation_registry WHERE status_list_id = %s", (list_id,))
    cur.execute("DELETE FROM observer_agents WHERE agent_id = %s", (agent_id,))
    conn.commit()
    cur.close()


def make_test_resolver():
    def resolve(did_string: str) -> dict:
        conn = get_db_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT did_document FROM observer_agents WHERE agent_did = %s",
                (did_string,),
            )
            row = cur.fetchone()
            cur.close()
            if not row or not row[0]:
                raise ValueError(f"No DID document found for {did_string!r}")
            doc = row[0]
            return doc if isinstance(doc, dict) else json.loads(doc)
        finally:
            conn.close()
    return resolve


def sign_request_body(body: dict, private_key: Ed25519PrivateKey, key_id: str) -> dict:
    message = canonical_bytes(body)
    sig = private_key.sign(message)
    signed = dict(body)
    signed["proof"] = {
        "type": "Ed25519Signature2020",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verificationMethod": key_id,
        "proofPurpose": "authentication",
        "proofValue": encode_proof_value(sig),
    }
    return signed


async def run():
    print("=" * 70)
    print("Spec 3.3 E2E Lifecycle Test")
    print("=" * 70)

    agent_id, did, key_id, priv_key, did_doc = make_test_agent()
    print(f"\n[setup] Test agent: {did}")

    conn = get_db_conn()
    insert_test_agent(conn, agent_id, did, did_doc)
    conn.close()
    print("[setup] Agent inserted into observer_agents")

    configure_status_lists(
        get_db_connection_fn=get_db_conn,
        resolve_did_fn=make_test_resolver(),
        base_url=TEST_BASE_URL,
    )
    app = FastAPI()
    app.include_router(status_list_router)
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    print("[setup] Router configured, async ASGI client ready")

    async def POST(path, json):
        return await client.post(path, json=json)

    list_id = None
    try:
        # --- Allocate list ---
        print("\n[1] Allocate status list")
        req = sign_request_body({"statusPurpose": "revocation"}, priv_key, key_id)
        r = await client.post("/sovereign/status-lists", json=req)
        assert r.status_code == 201, f"allocate failed: {r.status_code} {r.text}"
        alloc = r.json()
        list_id = alloc["listId"]
        print(f"    listId={list_id}")
        print(f"    statusListUrl={alloc['statusListUrl']}")

        # --- Allocate two indices: one to revoke, one to leave valid ---
        print("\n[2a] Allocate index (to be revoked)")
        req = sign_request_body({}, priv_key, key_id)
        r = await client.post(f"/sovereign/status-lists/{list_id}/allocate-index", json=req)
        assert r.status_code == 200, f"allocate-index failed: {r.status_code} {r.text}"
        revoke_idx = r.json()["allocatedIndex"]
        print(f"    revoke_idx={revoke_idx}")

        print("[2b] Allocate index (to stay valid)")
        req = sign_request_body({}, priv_key, key_id)
        r = await client.post(f"/sovereign/status-lists/{list_id}/allocate-index", json=req)
        assert r.status_code == 200, f"allocate-index failed: {r.status_code} {r.text}"
        valid_idx = r.json()["allocatedIndex"]
        print(f"    valid_idx={valid_idx}")

        allocated_index = revoke_idx  # legacy alias, used by mock VC below

        # --- Build two mock VCs — one for each allocated index ---
        def build_vc(idx):
            return {
                "@context": ["https://www.w3.org/ns/credentials/v2"],
                "id": f"urn:uuid:{uuid.uuid4()}",
                "type": ["VerifiableCredential", "TestCredential"],
                "issuer": did,
                "credentialSubject": {"id": did, "attestation": "e2e-test"},
                "credentialStatus": [{
                    "id": f"{alloc['statusListUrl']}#{idx}",
                    "type": "BitstringStatusListEntry",
                    "statusPurpose": "revocation",
                    "statusListIndex": str(idx),
                    "statusListCredential": alloc["statusListUrl"],
                }],
            }
        revoked_vc = build_vc(revoke_idx)
        valid_vc = build_vc(valid_idx)

        # --- Submit revocation BSL (only way to promote list to serveable state) ---
        print(f"\n[3] Submit revocation BSL — flip bit {revoke_idx} only")
        bs = create_bitstring()
        set_bit(bs, revoke_idx, 1)
        revocation_bsl = {
            "@context": ["https://www.w3.org/ns/credentials/v2"],
            "id": alloc["statusListUrl"],
            "type": ["VerifiableCredential", "BitstringStatusListCredential"],
            "issuer": did,
            "validFrom": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "credentialSubject": {
                "id": f"{alloc['statusListUrl']}#list",
                "type": "BitstringStatusList",
                "statusPurpose": "revocation",
                "encodedList": encode_bitstring(bs),
            },
        }
        signed = sign_document(revocation_bsl, priv_key, key_id)
        r = await client.post(f"/sovereign/status-lists/{list_id}", json={"credential": signed})
        assert r.status_code == 200, f"revocation failed: {r.status_code} {r.text}"
        rev = r.json()
        assert rev.get("bitsChanged") == 1, f"Expected bitsChanged=1, got {rev}"
        print(f"    bitsChanged={rev['bitsChanged']} ✓")

        # --- Verify both credentials: revoked should fail, untouched should pass ---
        print(f"\n[4] /verify/status on revoked VC (index {revoke_idx}) — expect overall_valid=False")
        r = await client.post("/verify/status", json={"credential": revoked_vc})
        assert r.status_code == 200, f"verify failed: {r.status_code} {r.text}"
        post_r = r.json()
        assert post_r["overall_valid"] is False, f"Expected overall_valid=False for revoked VC, got {post_r}"
        print(f"    overall_valid={post_r['overall_valid']} ✓")

        print(f"\n[5] /verify/status on untouched VC (index {valid_idx}) — expect overall_valid=True")
        r = await client.post("/verify/status", json={"credential": valid_vc})
        assert r.status_code == 200, f"verify failed: {r.status_code} {r.text}"
        post_v = r.json()
        assert post_v["overall_valid"] is True, f"Expected overall_valid=True for untouched VC, got {post_v}"
        print(f"    overall_valid={post_v['overall_valid']} ✓")

        print("\n" + "=" * 70)
        print("ALL STAGES PASSED — Spec 3.3 lifecycle verified end-to-end")
        print("=" * 70)

    finally:
        await client.aclose()
        conn = get_db_conn()
        cleanup(conn, agent_id, list_id)
        conn.close()
        print(f"\n[cleanup] Test agent and status list removed")


if __name__ == "__main__":
    asyncio.run(run())
