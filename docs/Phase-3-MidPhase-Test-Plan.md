# Phase 3 Mid-Phase Test Plan: Specs 3.1, 3.2, 3.3
**Date:** April 21, 2026
**Purpose:** Validate that Specs 3.1 (attestations), 3.2 (delegations), and 3.3 (revocation) work correctly individually AND in combination, before Phase 3 continues with Specs 3.4–3.8.
**Audience:** Maxi (executor), Boyd (observer/validator)
**References:** Specs 3.1, 3.2, 3.3; OP/AT Build Principles v0.2

---

## How to Use This Document

Each test has a **setup** section, a **steps** section with exact commands, and a **pass criteria** section with what success looks like. Maxi runs the steps; Boyd validates results match the criteria.

If a test fails:
- Note what failed and how (which step, what response, what expected).
- Categorize as: **minor** (test setup issue, ambiguous error message), **moderate** (implementation bug requiring fix), or **architectural** (escalate to spec discussion).
- Continue to the next test unless the failure blocks subsequent tests (Test 1 failing blocks most others; Test 8 failing blocks nothing).

Document results in-place under each test's "Results" section.

Substitute real values for `<placeholders>` as you go.

---

## Pre-Test Setup

### S.1 — Test identities

Create three test identities for use across all tests:

```bash
# Test issuer (KYB provider role)
ISSUER_DID="did:web:test-issuer.observerprotocol.org"
ISSUER_KEY_FILE="/tmp/test-issuer-key.json"

# Test principal (Sovereign individual)
PRINCIPAL_HANDLE="test-principal-001"
PRINCIPAL_DID="did:web:agenticterminal.io:sovereign:${PRINCIPAL_HANDLE}"
PRINCIPAL_KEY_FILE="/tmp/test-principal-key.json"

# Test agent (subject of delegations)
AGENT_DID="did:web:api.observerprotocol.org:agents:test:agent-001"
AGENT_KEY_FILE="/tmp/test-agent-key.json"
```

Generate Ed25519 keypairs for each, register the DID documents in OP, and confirm resolution:

```bash
# Replace with the actual key generation utility used in implementation
python scripts/generate_test_did.py --did $ISSUER_DID --key-out $ISSUER_KEY_FILE
python scripts/generate_test_did.py --did $PRINCIPAL_DID --key-out $PRINCIPAL_KEY_FILE
python scripts/generate_test_did.py --did $AGENT_DID --key-out $AGENT_KEY_FILE

# Confirm all three resolve
curl -s "https://api.observerprotocol.org/did/$(echo $ISSUER_DID | sed 's/:/%3A/g')" | jq .id
curl -s "https://api.observerprotocol.org/did/$(echo $PRINCIPAL_DID | sed 's/:/%3A/g')" | jq .id
curl -s "https://api.observerprotocol.org/did/$(echo $AGENT_DID | sed 's/:/%3A/g')" | jq .id
```

**Pass:** All three DIDs resolve and return their `id` field.
**If fail:** DID infrastructure is broken; do not proceed.

---

## Test 1 — Minimum Viable End-to-End Flow

**Goal:** Confirm Sovereign principal → agent delegation flow works through all three capabilities (3.1's verification pattern, 3.2's delegation, 3.3's status list).

### Setup
- Principal DID, agent DID resolvable (from S.1).
- Tier 3 status list allocated for the principal.

### Steps

**1.1 — Allocate a status list for the principal:**
```bash
# Authenticated as principal
curl -X POST https://api.observerprotocol.org/sovereign/status-lists \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PRINCIPAL_AUTH_TOKEN" \
  -d '{"statusPurpose": "revocation"}' \
  | jq .

# Capture the list_id and status_list_url from response
LIST_ID="<from response>"
STATUS_LIST_URL="<from response>"
```

**1.2 — Allocate an index on the status list:**
```bash
curl -X POST "https://api.observerprotocol.org/sovereign/status-lists/${LIST_ID}/allocate-index" \
  -H "Authorization: Bearer $PRINCIPAL_AUTH_TOKEN" \
  | jq .

# Capture the index from response
INDEX="<from response>"
```

**1.3 — Construct and sign a delegation credential** (principal → agent):

Use the implementation's signing utility to produce a `DelegationCredential` with:
- `issuer`: $PRINCIPAL_DID
- `credentialSubject.id`: $AGENT_DID
- `actionScope`: `{ "allowed_rails": ["lightning"], "per_transaction_ceiling": {"amount": "100.00", "currency": "USD"} }`
- `delegationScope`: `{ "may_delegate_further": false }`
- `enforcementMode`: `pre_transaction_check`
- `parentDelegationId`: null
- `credentialStatus`: `[{ "id": "${STATUS_LIST_URL}#${INDEX}", "type": "BitstringStatusListEntry", "statusPurpose": "revocation", "statusListIndex": "${INDEX}", "statusListCredential": "${STATUS_LIST_URL}" }]`

Save the signed credential as `/tmp/test1-delegation.json`.

**1.4 — Submit the delegation for Tier 3 hosting:**
```bash
curl -X POST https://api.observerprotocol.org/sovereign/delegations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PRINCIPAL_AUTH_TOKEN" \
  -d @/tmp/test1-delegation.json \
  | jq .

# Capture the hosting URL from response
DELEGATION_URL="<from response>"
```

**1.5 — Verify the delegation as a counterparty:**
```bash
curl -X POST https://api.observerprotocol.org/verify/delegation \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test1-delegation.json), \"resolve_chain\": true}" \
  | jq .
```

**1.6 — Check status:**
```bash
curl -X POST https://api.observerprotocol.org/verify/status \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test1-delegation.json)}" \
  | jq .
```

### Pass criteria
- Step 1.1 returns a `list_id` and `status_list_url`.
- Step 1.2 returns an integer index (likely 0 for a fresh list).
- Step 1.4 returns a hosting URL matching pattern `https://api.observerprotocol.org/sovereign/delegations/${PRINCIPAL_HANDLE}/<id>`.
- Step 1.5 returns `verified: true` with all checks passing (signature, schema, validity_period, attenuation, no_cycles, chain_complete).
- Step 1.6 returns `overall_valid: true` with the revocation bit at the index reading 0.

### Results
*To be filled in by Maxi.*

---

## Test 2 — Revocation Propagation

**Goal:** Confirm that revoking a delegation via 3.3's status list update is correctly reflected in subsequent verifications.

### Setup
- Test 1 must have passed.
- The delegation from Test 1 still exists, valid, with status bit at 0.

### Steps

**2.1 — Fetch the current status list:**
```bash
curl -s ${STATUS_LIST_URL} > /tmp/test2-status-list-before.json
cat /tmp/test2-status-list-before.json | jq .
```

**2.2 — Construct an updated status list with the bit at INDEX flipped to 1:**

Use the implementation's status list utility to:
- Decode the bitstring from `/tmp/test2-status-list-before.json` (`encodedList` field).
- Flip the bit at position INDEX from 0 to 1.
- Re-encode the bitstring.
- Construct an updated `BitstringStatusListCredential` with the new bitstring.
- Sign with PRINCIPAL_KEY_FILE.

Save as `/tmp/test2-status-list-after.json`.

**2.3 — Submit the updated status list:**
```bash
curl -X POST "https://api.observerprotocol.org/sovereign/status-lists/${LIST_ID}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PRINCIPAL_AUTH_TOKEN" \
  -d "{\"credential\": $(cat /tmp/test2-status-list-after.json)}" \
  | jq .
```

**2.4 — Re-check status of the original delegation:**
```bash
curl -X POST https://api.observerprotocol.org/verify/status \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test1-delegation.json)}" \
  | jq .
```

**2.5 — Re-verify the delegation:**
```bash
curl -X POST https://api.observerprotocol.org/verify/delegation \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test1-delegation.json), \"resolve_chain\": true}" \
  | jq .
```

### Pass criteria
- Step 2.3 returns success (the update was accepted by OP's authority verification).
- Step 2.4 returns `overall_valid: false` with `current_value: 1` for the revocation entry.
- Step 2.5 — behavior depends on whether `/verify/delegation` integrates the status check. Per Spec 3.2 §5.1 step 5, status checking is part of verification once 3.3 is present. Expected: `verified: false` with a status-related check failing.

### Results
*To be filled in by Maxi.*

---

## Test 3 — Attestation as Delegation KYB Link

**Goal:** Confirm that 3.1 attestations and 3.2 delegations integrate correctly via the `kybCredentialId` field.

### Setup
- ISSUER_DID resolvable.
- An organization DID for the delegation issuer:
  ```bash
  ORG_DID="did:web:test-org.observerprotocol.org"
  ORG_KEY_FILE="/tmp/test-org-key.json"
  python scripts/generate_test_did.py --did $ORG_DID --key-out $ORG_KEY_FILE
  ```

### Steps

**3.1 — Issuer constructs and signs a KYB attestation about the org:**

Use signing utility to produce a `KYBAttestationCredential` with:
- `issuer`: $ISSUER_DID
- `credentialSubject.id`: $ORG_DID
- `credentialSubject.legalName`: "Test Org Ltd"
- `credentialSubject.jurisdiction`: "US-DE"
- `credentialSubject.kybLevel`: "standard"
- `validUntil`: 1 year from now

Save as `/tmp/test3-kyb-attestation.json`.

The Issuer hosts this at a URL — for the test, simulate by serving it from a local web server or use the OP convenience hosting if available. Capture as `KYB_VC_URL`.

**3.2 — Verify the KYB attestation independently:**
```bash
curl -X POST https://api.observerprotocol.org/verify \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test3-kyb-attestation.json)}" \
  | jq .
```

Expected: `verified: true`.

**3.3 — Org issues a delegation to the agent referencing the KYB:**

Construct a `DelegationCredential` with:
- `issuer`: $ORG_DID
- `credentialSubject.id`: $AGENT_DID
- `actionScope`: a representative action scope
- `delegationScope`: `{ "may_delegate_further": false }`
- `enforcementMode`: `pre_transaction_check`
- `parentDelegationId`: null
- `kybCredentialId`: $KYB_VC_URL
- `credentialStatus`: omitted for this test (or use a separately allocated status list if convenient)

Sign with ORG_KEY_FILE. Save as `/tmp/test3-delegation.json`.

**3.4 — Verifier verifies the delegation AND follows the KYB link:**
```bash
curl -X POST https://api.observerprotocol.org/verify/delegation \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test3-delegation.json), \"resolve_chain\": true}" \
  | jq .
```

Then independently fetch the KYB at `kybCredentialId` and verify it:
```bash
curl -s ${KYB_VC_URL} > /tmp/test3-kyb-fetched.json
diff /tmp/test3-kyb-attestation.json /tmp/test3-kyb-fetched.json
curl -X POST https://api.observerprotocol.org/verify \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test3-kyb-fetched.json)}" \
  | jq .
```

### Pass criteria
- Step 3.2 verifies the KYB attestation as `verified: true`.
- Step 3.4 verifies the delegation as `verified: true`.
- The fetched KYB at `kybCredentialId` is byte-identical to the issued KYB (no tampering, hosting works).
- The fetched KYB independently verifies as `verified: true`.

**Note:** Spec 3.2 §4.7 makes the KYB link optional for verification (counterparty applies their own policy). So `/verify/delegation` is not REQUIRED to follow the KYB link. The test confirms the link is fetchable and the linked credential is independently valid — the integration works in the sense that a counterparty CAN make the policy decision.

### Results
*To be filled in by Maxi.*

---

## Test 4 — Multi-Edge Chain with Mid-Chain Revocation

**Goal:** Confirm 3.2 chain verification correctly handles 3.3 revocation in the middle of a chain (cascade behavior).

### Setup
- Three DIDs: ROOT, MIDDLE, LEAF.
  ```bash
  ROOT_DID="did:web:test-root.observerprotocol.org"
  MIDDLE_DID="did:web:test-middle.observerprotocol.org"
  LEAF_DID="did:web:api.observerprotocol.org:agents:test:agent-leaf"
  ```
  Generate keys and register DIDs.
- A status list for ROOT and a status list for MIDDLE (so each can revoke their respective delegations).

### Steps

**4.1 — ROOT issues delegation to MIDDLE:**

Construct a `DelegationCredential`:
- `issuer`: $ROOT_DID
- `credentialSubject.id`: $MIDDLE_DID
- `actionScope`: broad scope (e.g., `per_transaction_ceiling: 1000.00`, all rails)
- `delegationScope`: `{ "may_delegate_further": true, "max_child_action_scope": { ... }, "may_delegate_delegation_authority": false }`
- `parentDelegationId`: null
- `credentialStatus`: pointing at ROOT's status list

Sign with ROOT_KEY_FILE. Save as `/tmp/test4-root-delegation.json`.
Host at a URL: $ROOT_DELEGATION_URL.

**4.2 — MIDDLE issues delegation to LEAF:**

Construct a `DelegationCredential`:
- `issuer`: $MIDDLE_DID
- `credentialSubject.id`: $LEAF_DID
- `actionScope`: narrower than ROOT's (e.g., `per_transaction_ceiling: 500.00`, subset of rails)
- `delegationScope`: `{ "may_delegate_further": false }`
- `parentDelegationId`: $ROOT_DELEGATION_URL
- `credentialStatus`: pointing at MIDDLE's status list

Sign with MIDDLE_KEY_FILE. Save as `/tmp/test4-middle-delegation.json`.
Host at a URL: $MIDDLE_DELEGATION_URL.

**4.3 — Verify the LEAF delegation (full chain):**
```bash
curl -X POST https://api.observerprotocol.org/verify/delegation \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test4-middle-delegation.json), \"resolve_chain\": true}" \
  | jq .
```

Expected: `verified: true`, chain length 2, attenuation passes.

**4.4 — ROOT revokes the MIDDLE delegation:**

Update ROOT's status list to flip the bit for MIDDLE's index. Sign and submit per Test 2 pattern. (If ROOT is a Tier 2 host, this is a Tier 2 update flow; if Tier 3 / OP-hosted, use the OP endpoints.)

**4.5 — Re-verify the LEAF delegation:**
```bash
curl -X POST https://api.observerprotocol.org/verify/delegation \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test4-middle-delegation.json), \"resolve_chain\": true}" \
  | jq .
```

### Pass criteria
- Step 4.3 returns `verified: true` with a 2-link chain.
- Step 4.4 succeeds (ROOT had authority to revoke MIDDLE's delegation per ACL-on-chain).
- Step 4.5 returns `verified: false` because the MIDDLE delegation is now revoked, even though LEAF's own delegation hasn't been touched. This is the cascade behavior from Spec 3.3 §6.4.

### Results
*To be filled in by Maxi.*

---

## Test 5 — Cross-Tier Chain

**Goal:** Confirm chains mixing Tier 2 (Issuer-hosted) and Tier 3 (OP-hosted) URLs verify correctly.

### Setup
- An organization with Tier 2 hosting capability (use a test domain or a local web server simulating one).
- A Sovereign principal under the org (Tier 3 hosting via OP).

### Steps

**5.1 — Org issues delegation to a sub-org or department, hosted at the org's domain (Tier 2):**

Construct delegation, sign, host at `https://test-org.observerprotocol.org/delegations/dept-001`.
Save credential as `/tmp/test5-tier2-parent.json`.

**5.2 — Sub-org/department (or in this case, a Sovereign individual representing them) issues a child delegation, hosted via OP (Tier 3):**

Construct delegation with `parentDelegationId: "https://test-org.observerprotocol.org/delegations/dept-001"`.
Submit via Sovereign hosting per Test 1 pattern.
Save as `/tmp/test5-tier3-child.json`.

**5.3 — Verify the child:**
```bash
curl -X POST https://api.observerprotocol.org/verify/delegation \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test5-tier3-child.json), \"resolve_chain\": true}" \
  | jq .
```

### Pass criteria
- Step 5.3 returns `verified: true` with a 2-link chain.
- The chain output shows one Tier 2 URL and one Tier 3 URL, both successfully resolved and verified.
- No errors related to URL pattern handling, fetch behavior, or cross-domain resolution.

### Results
*To be filled in by Maxi.*

---

## Test 6 — Decentralization Conformance

**Goal:** Confirm verification flows work with OP API unreachable, using only cached state.

### Setup
- A test client with the ability to:
  - Pre-cache DID documents locally.
  - Pre-cache credential schemas locally.
  - Pre-cache status list credentials locally.
  - Block network access to `api.observerprotocol.org` during the test.

### Steps

**6.1 — Pre-cache:**

Fetch and locally cache:
- DID documents for ISSUER_DID, PRINCIPAL_DID, AGENT_DID, ROOT_DID, MIDDLE_DID, ORG_DID.
- Schemas for `kyb-attestation/v1.json`, `delegation/v1.json`.
- Status list credentials referenced by Test 1's delegation.

**6.2 — Block OP API access:**
```bash
# Simulate unreachable OP — adapt to local network setup
sudo iptables -A OUTPUT -d api.observerprotocol.org -j DROP
# Or use /etc/hosts to redirect to invalid IP
```

**6.3 — Run verification flows using only cached state:**

A test client that:
- Reads the credential from local file.
- Resolves DID using the local cache (not OP's resolver).
- Validates schema using the local cached schema.
- Checks status using the local cached status list.
- Verifies signature using the cached DID document.

This requires that the verification logic in the implementation can be invoked WITHOUT calling OP's verification endpoint. If the only way to verify is to POST to `/verify/delegation`, this test cannot pass — that's a finding.

**6.4 — Restore OP access:**
```bash
sudo iptables -D OUTPUT -d api.observerprotocol.org -j DROP
```

### Pass criteria
- Step 6.3 succeeds — verification returns `verified: true` for valid credentials, `verified: false` for revoked ones, all without any network call to OP.
- The implementation provides verification logic accessible to clients (a library, a local function, an SDK) that does not require network calls to OP.

**Note:** This test is the most likely to surface a real issue, because the convenience verification endpoint pattern can lead to over-reliance on OP being reachable. If verification only works via OP's endpoint, the decentralization conformance property is violated even if everything else works.

### Results
*To be filled in by Maxi. This is the most important test — note results carefully.*

---

## Test 7 — RevocationAgent Pattern

**Goal:** Confirm a delegated agent can sign status list updates on behalf of a principal, and that revoking the agent's delegation correctly stops further updates.

### Setup
- PRINCIPAL_DID with an existing status list (from Test 1).
- A new DID for the RevocationAgent:
  ```bash
  REVOKER_DID="did:web:api.observerprotocol.org:agents:test:revoker-001"
  REVOKER_KEY_FILE="/tmp/test-revoker-key.json"
  python scripts/generate_test_did.py --did $REVOKER_DID --key-out $REVOKER_KEY_FILE
  ```

### Steps

**7.1 — Principal issues a delegation to REVOKER_DID:**

Construct a `DelegationCredential`:
- `issuer`: $PRINCIPAL_DID
- `credentialSubject.id`: $REVOKER_DID
- `actionScope`: includes authority to "sign status list updates for status lists owned by $PRINCIPAL_DID" (representation: include `status_list_signing` in `allowed_rails` or use a custom action scope field; whatever the implementation supports).
- `delegationScope`: `{ "may_delegate_further": false }`
- `parentDelegationId`: null

Sign with PRINCIPAL_KEY_FILE. Submit via Sovereign hosting. Save as `/tmp/test7-revoker-delegation.json`.

**7.2 — Issue another credential under the principal's status list:**

Per Test 1 pattern, allocate an index and issue a new credential with `credentialStatus` referencing the principal's status list.

**7.3 — RevocationAgent updates the status list to revoke the credential from 7.2:**

The agent fetches the status list, flips the appropriate bit, signs with REVOKER_KEY_FILE, and submits via the OP endpoint.

```bash
curl -X POST "https://api.observerprotocol.org/sovereign/status-lists/${LIST_ID}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $REVOKER_AUTH_TOKEN" \
  -d "{\"credential\": $(cat /tmp/test7-status-update.json)}" \
  | jq .
```

Expected: success. OP's authority verification walks the chain, finds REVOKER's delegation from PRINCIPAL with status-list-signing authority, accepts.

**7.4 — Verify the revocation took effect:**
```bash
curl -X POST https://api.observerprotocol.org/verify/status \
  -H "Content-Type: application/json" \
  -d "{\"credential\": $(cat /tmp/test7-credential.json)}" \
  | jq .
```

**7.5 — Principal revokes the REVOKER's delegation:**

Update principal's status list to revoke the delegation from 7.1.

**7.6 — RevocationAgent attempts another update:**

Try the same operation as 7.3 with a different credential. OP should now reject because the agent's authority has been revoked.

### Pass criteria
- Step 7.3 succeeds (authority verification passes).
- Step 7.4 shows the credential as revoked.
- Step 7.5 succeeds (principal revoking their own delegation).
- Step 7.6 fails with an authority error (the agent's delegation is no longer valid, so they cannot sign status list updates).

### Results
*To be filled in by Maxi. This is the most architecturally significant test — confirms the RevocationAgent pattern works as designed.*

---

## Test 8 — Concurrent Operations

**Goal:** Confirm atomic operations (index allocation, status list updates) handle concurrency correctly.

### Setup
- A status list owned by PRINCIPAL_DID with several free indices.

### Steps

**8.1 — Concurrent index allocation:**

Send 10 simultaneous index allocation requests:
```bash
for i in {1..10}; do
  curl -X POST "https://api.observerprotocol.org/sovereign/status-lists/${LIST_ID}/allocate-index" \
    -H "Authorization: Bearer $PRINCIPAL_AUTH_TOKEN" \
    | jq -r .index &
done
wait
```

### Pass criteria
- Step 8.1 returns 10 distinct, sequential integer indices. No duplicates. No skipped numbers (or if numbers are skipped, document the policy — some implementations may use skipping for safety).

### Results
*To be filled in by Maxi.*

---

## Phase 3 Mid-Phase Test Summary

After completing tests, fill in:

| Test | Result | Severity if failed | Notes |
|---|---|---|---|
| 1 — Minimum viable end-to-end | | | |
| 2 — Revocation propagation | | | |
| 3 — Attestation as KYB link | | | |
| 4 — Multi-edge chain with revocation | | | |
| 5 — Cross-tier chain | | | |
| 6 — Decentralization conformance | | | |
| 7 — RevocationAgent pattern | | | |
| 8 — Concurrent operations | | | |

---

## What to Do With Results

**All pass:** Phase 3 foundation is solid. Continue with Specs 3.4–3.8 confidently.

**Minor failures only:** Note for phase-end cleanup. Do not block 3.4 drafting.

**Moderate failures:** Fix before 3.4 ships. Each capability after 3.3 may depend on the broken behavior. The cost of fixing now is meaningfully less than fixing after more layers stack on top.

**Architectural failures:** Stop and discuss. May trigger a revisit with Leo on the affected capability's architecture, or a spec revision. Specifically:
- Test 6 (decentralization conformance) failing is architectural — the protocol's value proposition depends on this property holding.
- Test 7 (RevocationAgent pattern) failing is architectural — Leo's "OP doesn't automate, users delegate" principle depends on this working.
- Test 4 (cascade behavior) failing is architectural — the ACL-on-chain model depends on this.

Other failures are typically moderate or minor and can be fixed without protocol-level rework.

---

*This test plan is aligned to Build Principles v0.2 and Specs 3.1, 3.2, 3.3 as of April 21, 2026.*
