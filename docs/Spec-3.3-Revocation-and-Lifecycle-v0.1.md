# Spec 3.3 — Revocation and Lifecycle
**Phase:** 3
**Capability:** 3 of 8
**Version:** 0.1
**Date:** April 21, 2026
**Authors:** Boyd Cohen, Claude
**Status:** Ready for implementation
**References:** OP/AT Build Principles v0.2, Spec 3.1 (Third-Party Attestations), Spec 3.2 (Delegation Credentials)

---

## 1. Purpose

This spec defines how credentials issued under Specs 3.1 and 3.2 are revoked or suspended after issuance, how status changes propagate to verifiers, and how revocation authority is determined and enforced. It closes the transitional state both prior specs left open.

The mechanism is W3C Bitstring Status List v1.0. The authority model is ACL-on-chain: original Issuers retain revocation authority over credentials they issued, and parent-chain Issuers (for delegation chains) inherit it. Status list updates are signed by the Issuer using their own key, hosted at one of three tiers depending on the Issuer's infrastructure.

## 2. Scope

### In scope

- Bitstring Status List v1.0 infrastructure (creation, update, retrieval)
- The `credentialStatus` field added to credentials issued under Specs 3.1 and 3.2
- Status list hosting at all three tiers (Issuer-hosted Tier 2, OP-hosted Tier 3)
- Revocation authority model for attestations (Issuer-only)
- Revocation authority model for delegations (ACL-on-chain)
- Mid-transaction revocation behavior
- Suspension as distinct from revocation
- Cascade behavior when parent delegations are revoked
- AT-side cache invalidation when source credentials are revoked
- The RevocationAgent pattern for automated revocation
- Database schema for OP-hosted status lists (`vac_revocation_registry`)

### Out of scope

- DID key compromise handling — this is a DID-layer operation (DID document update, key rotation), not an AIP-layer revocation. Future DID lifecycle spec will address this.
- Sovereign UI for revocation actions (Spec 3.7)
- Enterprise dashboard UI for revocation management (Spec 3.8)
- The notification specifics for "principal action required" alerts — this spec specifies that AT MUST notify, not the channels or content (left for Spec 3.7/3.8)
- Implementation of any specific RevocationAgent — this spec documents the pattern; building agents is downstream of the protocol

### Dependencies

- Spec 3.1 (attestations) implementation complete. The `credentialStatus` field is added to attestation credentials by this spec; without 3.1's verification pipeline, there is nothing to add it to.
- Spec 3.2 (delegations) implementation complete. Same reasoning — delegation credentials gain `credentialStatus` here.
- Ed25519 signing infrastructure operational (Phase 2, complete).
- DID resolution endpoint live (Phase 2, complete).
- `vac_revocation_registry` table exists in `agentic_terminal_db` (exists; schema replacement required).

## 3. Mechanism: Bitstring Status List v1.0

### 3.1 What it is

Bitstring Status List v1.0 is a W3C Recommendation (May 2025) for publishing the status of verifiable credentials. The mechanism is:

- Each Issuer maintains one or more status lists, each a bitstring of fixed minimum length (131,072 bits / 16KB uncompressed).
- Each issued credential is assigned an integer index within one of the Issuer's status lists.
- A bit value of 0 at that index means the credential is in good standing for the list's `statusPurpose`. A bit value of 1 means it has been actioned on (revoked or suspended).
- The status list is itself a W3C Verifiable Credential (`BitstringStatusListCredential`), signed by the Issuer, hosted at a stable URL.
- Verifiers fetch the status list, verify its signature, decode the bitstring, and check the bit at the specific credential's index.

This mechanism is privacy-preserving (verifiers cannot tell which specific credential is being checked from the network request, because the entire list is fetched), space-efficient (16KB holds 131,072 credentials), and high-performance (status checks are bitwise operations after one HTTP fetch).

### 3.2 Two `statusPurpose` values

AIP uses two purposes:

- `revocation` — permanent invalidation. Once the bit is set to 1, the credential is dead. The bit MAY be reset to 0 in error-correction cases but the protocol treats revocation as terminal.
- `suspension` — temporary invalidation. The bit may flip between 0 and 1 freely. Used for "pause my agent's authorization while I'm on vacation" type scenarios.

A single credential MAY carry multiple `credentialStatus` entries with different purposes (one for revocation, one for suspension). Verifiers check all of them; any bit set to 1 for any purpose invalidates the credential for that purpose.

### 3.3 Why this mechanism over alternatives

For completeness and to head off questions during implementation: alternatives considered included a centralized revocation registry queried per credential (privacy-leaking and bandwidth-heavy), revocation lists in DID documents (limited size, awkward updates), and short-lived credentials with continuous re-issuance (high operational cost, bad UX for principals). Bitstring Status List wins on all three axes — privacy, efficiency, standardization — and is the W3C consensus mechanism. Build against it.

## 4. The `credentialStatus` Field

### 4.1 Addition to existing credential schemas

This spec adds a `credentialStatus` field to credentials issued under Specs 3.1 and 3.2. The field structure follows Bitstring Status List v1.0:

```json
"credentialStatus": [
  {
    "id": "https://<issuer-or-op-hosting>/status/<list-id>#<index>",
    "type": "BitstringStatusListEntry",
    "statusPurpose": "revocation",
    "statusListIndex": "<integer>",
    "statusListCredential": "https://<issuer-or-op-hosting>/status/<list-id>"
  }
]
```

The field is an array because credentials may carry multiple status entries (one for revocation, one for suspension, etc.). For credentials carrying only revocation, the array contains one element.

### 4.2 Required vs. optional

`credentialStatus` is REQUIRED for:

- All `DelegationCredential` issued under Spec 3.2.
- `KYBAttestationCredential`, `KYAAttestationCredential`, `ComplianceAttestationCredential`, `NetworkMembershipCredential` issued under Spec 3.1.

`credentialStatus` is FORBIDDEN for:

- Any non-revokable credential (Tier 1 hosting per Build Principles §2.3). Specifically: transaction receipts, point-in-time completion attestations, any credential whose semantics make revocation incoherent.

The distinction maps to the hosting tier the credential targets. Tier 1 = no `credentialStatus`. Tier 2 and Tier 3 = `credentialStatus` required.

### 4.3 Schema versioning impact

Adding `credentialStatus` to credentials previously issued without it is a schema change. The schemas under `https://observerprotocol.org/schemas/<type>/v1.json` are updated to make `credentialStatus` required. Credentials issued by Spec 3.1's implementation before Spec 3.3 lands will be valid against the v1 schema until the schema update is published, then technically non-conformant after.

The migration approach: bump the schemas to v2 and have new issuance reference `credentialSchema: ".../v2.json"` while old credentials continue validating against `.../v1.json`. This preserves the schema-versioning principle from Build Principles §4.4 (old URLs remain valid forever; breaking changes get new URLs).

This means the implementation order matters: the v2 schemas land first, then issuance pipelines move to issuing against v2, then any tooling that was validating against v1 hardcoded paths is updated. Maxi handles this in §10.

## 5. Hosting

### 5.1 Tier 2: Issuer-hosted status lists

Default for Issuers with their own infrastructure. The Issuer:

1. Generates a status list (a bitstring of at least 131,072 bits, all zeros initially).
2. Wraps it in a `BitstringStatusListCredential` VC, signed with their own DID.
3. Hosts the signed VC at a stable URL on their domain (e.g., `https://kyb.example.com/status/list-001`).
4. Assigns indices to credentials they issue, embedding the `credentialStatus` field with the URL and index.
5. To revoke: flips the bit at the credential's index to 1, re-signs the `BitstringStatusListCredential`, publishes the new version at the same URL.

The status list URL MUST remain stable. Versioning is implicit in the credential's `proof.created` timestamp and (optionally) a `validFrom` field on the status list itself.

### 5.2 Tier 3: OP-hosted status lists

For Issuers without their own infrastructure (Sovereign principals, small organizations). OP serves the status list bytes; the Issuer signs them.

The flow:

1. Issuer requests OP allocate a status list for them via `POST https://api.observerprotocol.org/sovereign/status-lists`. OP responds with a list ID and the URL where the list will be hosted.
2. When the Issuer wants to issue a credential, they request the next available index from OP via `POST https://api.observerprotocol.org/sovereign/status-lists/<list-id>/allocate-index`. OP responds with an integer.
3. Issuer constructs the credential with `credentialStatus` referencing the allocated URL and index, signs the credential, and proceeds.
4. To revoke: Issuer fetches the current `BitstringStatusListCredential` from OP, decodes the bitstring, flips the appropriate bit, re-encodes, signs the updated `BitstringStatusListCredential`, and submits via `POST https://api.observerprotocol.org/sovereign/status-lists/<list-id>` (the body is the freshly-signed credential).
5. OP validates the submitted credential (signature matches the list's authorized Issuer DID, structure conforms to Bitstring Status List v1.0) and serves it at the canonical URL.

OP never signs status lists. OP serves what the Issuer signs. If the Issuer's key is unavailable, OP cannot perform the revocation. This is the "OP hosts bytes, never keys" principle from Build Principles §2.1, applied to status lists specifically.

### 5.3 Mixed-tier verification

A counterparty verifying a credential follows the URL in `credentialStatus.statusListCredential` regardless of tier. Tier 2 URLs resolve to issuer infrastructure; Tier 3 URLs resolve to OP. From the verifier's perspective the two are identical — both return a signed `BitstringStatusListCredential`, both are verified the same way (signature against the Issuer's DID, bitstring decoded, index checked).

## 6. Revocation Authority

### 6.1 Attestations: Issuer-only

For credentials issued under Spec 3.1 (third-party attestations), only the original Issuer has authority to revoke. The Issuer flips the bit in their status list. There is no chain of authority because attestations have no chain — each is a bilateral assertion from Issuer to Subject.

If the Issuer wants to delegate revocation authority to another party (e.g., a compliance officer at a KYB provider), they do so through their own internal systems. The `BitstringStatusListCredential` is still signed by the Issuer's DID; who at the Issuer holds the key and authorizes the signing is internal to the Issuer's organization, invisible to AIP.

### 6.2 Delegations: ACL-on-chain

For credentials issued under Spec 3.2 (delegations), revocation authority follows the delegation graph itself. The model:

- The original Issuer of a delegation has revocation authority over that delegation. (Implicit, always.)
- Any ancestor Issuer in the chain (parent's parent, parent's parent's parent, etc.) inherits revocation authority over downstream delegations. (Implicit, always.)
- Additional parties may be granted revocation authority via the `acl.revocation_authority` field in the delegation credential. (Explicit, optional.)

Combined: the set of parties authorized to revoke a delegation is the union of the implicit ancestor authorities and the explicit ACL authorities.

### 6.3 Verification of revocation authority

When OP receives a status list update for a delegation (Tier 3 case), it MUST verify that the signing party has revocation authority for the credentials whose bits are being flipped. The check:

1. Identify which credentials' bits changed from 0 to 1 in the new status list.
2. For each such credential, fetch the credential's full chain (using the recursive query pattern from Spec 3.2 §8.2).
3. Verify that the DID signing the status list update is in the union of: (a) the credential's original Issuer, (b) any ancestor Issuer in the chain, (c) any DID listed in `acl.revocation_authority` on the credential.
4. If verification fails for any credential, OP rejects the entire status list update.

This applies only to Tier 3 (OP-hosted) status lists. Tier 2 status lists are hosted by Issuers themselves; Issuers are responsible for enforcing their own authority model. Counterparties verifying Tier 2 status lists trust that the signing key on the list belongs to a party authorized to revoke (because the same key is the Issuer's key, by definition).

### 6.4 Cascade behavior

When a parent delegation in a chain is revoked, all descendant delegations are implicitly invalid — not because their bits flip in their own status lists, but because chain verification (Spec 3.2 §5.2) fails when a parent is revoked.

This means: an Issuer revoking a parent delegation does NOT need to also revoke every descendant. The descendants become invalid automatically at verification time. Verifiers walking the chain encounter the revoked parent and reject the entire chain.

Issuers MAY additionally revoke descendants explicitly (for audit clarity, or to prevent cached descendant credentials from being trusted by verifiers with stale parent status). This is a defensive practice, not a protocol requirement.

The cascade is at verification time, not at revocation time. This matters for the implementation: revoking a parent does NOT trigger a batch update of descendant status lists. The protocol does not propagate revocations explicitly. It propagates them implicitly through chain verification.

## 7. Suspension

### 7.1 Mechanics

Suspension uses the same Bitstring Status List mechanism with `statusPurpose: "suspension"` instead of `"revocation"`. A suspended credential is invalid while suspended; flipping the bit back to 0 restores validity.

Credentials carrying both purposes have two `credentialStatus` entries (one for revocation, one for suspension), typically pointing at different status lists since different lists track different purposes.

### 7.2 When to use suspension vs. revocation

Suspension is appropriate when:

- A principal wants to temporarily pause their agent's authorization (vacation, troubleshooting, holding while reviewing recent activity).
- An organization wants to investigate a flagged delegation without permanently revoking it.
- A scheduled time-bound restriction applies (e.g., "no transactions during weekends" implemented as automated suspension/un-suspension).

Revocation is appropriate when:

- A credential should never be valid again.
- A key is suspected compromised.
- A delegation is being permanently terminated.

The choice is the Issuer's. The protocol supports both equally.

### 7.3 Verification semantics

Verifiers MUST check all `credentialStatus` entries on a credential and treat the credential as invalid if any bit (revocation or suspension) is set. There is no priority between purposes — any active status flag invalidates the credential.

## 8. Mid-Transaction Revocation Behavior

### 8.1 The race condition

A delegation may be revoked while a transaction authorized under it is in flight. The behavior depends on transaction state at the moment of revocation:

- **Not yet broadcast.** The transaction has been signed by the agent but not yet sent to the rail (e.g., sitting in a wallet queue, awaiting a final confirmation step). Revocation MUST invalidate the transaction. AT or whatever pre-transaction enforcement layer is in place MUST refuse to broadcast.
- **Broadcast but not yet confirmed.** The transaction is on the rail awaiting confirmation (Lightning routing, blockchain mempool, etc.). Revocation MUST cause the transaction to fail confirmation. For protocol-native enforcement (OWS) this happens because the rail consults the policy and the policy now reads "not authorized." For pre-transaction-check enforcement, AT may not be able to prevent confirmation; the transaction may complete on-rail and the Issuer is left with after-the-fact remediation (chargeback, dispute, etc.).
- **Confirmed.** The transaction is final. Revocation cannot reverse it. The credential is revoked going forward; the historical transaction stands.

This means: revocation's effectiveness is bounded by the rail's enforcement model and the timing of the transaction relative to the revocation event. Protocol-native enforcement (OWS) gives the strongest guarantees. Pre-transaction-check enforcement guarantees only "not yet broadcast" cases. No enforcement model can reverse confirmed transactions.

### 8.2 Implications for counterparties

Counterparties accepting transactions under delegations SHOULD check status at transaction-acceptance time, not just at credential-presentation time. A counterparty that fetches the delegation, verifies its status, and then proceeds to a multi-step transaction process risks the credential being revoked between verification and final acceptance.

The defensive pattern: re-check status immediately before the transaction is final. For low-value transactions this overhead may not be justified. For high-value transactions it is essential.

### 8.3 Implications for Issuers

Issuers revoking a delegation MUST understand that they cannot retroactively invalidate transactions already confirmed. Revocation is going-forward only.

For situations where retroactive invalidation matters (e.g., fraud discovered after-the-fact), the remediation is at the rail level — chargebacks, disputes, civil action — not at the credential level. AIP provides cryptographic evidence to support such remediation but does not perform the remediation itself.

## 9. Automating Revocation: The RevocationAgent Pattern

### 9.1 Why automation matters

Some revocation scenarios benefit from automation:

- Time-bound credentials whose expiry should trigger explicit revocation (rather than relying solely on `validUntil`).
- Fraud signals that should trigger immediate revocation without waiting for a human to act.
- Scheduled suspension/un-suspension cycles (the "no weekend transactions" example).
- Bulk revocation in response to a discovered compromise.

A naive implementation would have OP perform these revocations on the principal's behalf. AIP rejects this approach. OP signs nothing; OP serves bytes. Automating revocation through OP would violate the decentralization posture from Build Principles §2.1.

### 9.2 The pattern

The supported approach is for the principal to delegate revocation authority to an agent that performs the automation. The mechanics:

1. Principal issues a delegation credential to a `RevocationAgent` DID. The credential's action scope authorizes the agent to "sign status list updates for status lists owned by this principal." The credential's delegation scope is `may_delegate_further: false` (the agent cannot further delegate this authority).
2. The agent runs wherever the principal chooses — a cloud function, a home server, a third-party managed service.
3. The agent monitors whatever conditions the principal cares about (time triggers, fraud signals, scheduled rules, etc.).
4. When a condition triggers, the agent fetches the relevant status list, computes the updated bitstring, signs the new `BitstringStatusListCredential` with its own key, and submits it via the same Tier 3 hosting endpoint Sovereign principals use.
5. OP's revocation authority check (§6.3) sees that the signing DID is the RevocationAgent, walks the delegation chain, finds the principal's delegation authorizing the agent, and accepts the update.

The agent is, from the protocol's perspective, an Issuer with delegated authority. There is no special "revocation agent" credential type; it's just a delegation with an action scope that includes status-list-signing.

### 9.3 What this enables

- **Third-party RevocationAgent services** can offer "revocation-as-a-service" to Issuers who want automation without running infrastructure. Multiple competing services can exist; they all interoperate because they all use the same protocol primitives.
- **Different automation strategies** can coexist for the same principal. A principal might delegate time-trigger automation to one agent and fraud-signal monitoring to another, each with narrowly scoped authority.
- **Audit and reversibility.** The principal can inspect what their RevocationAgent has done by querying the status lists. They can revoke the agent's delegation at any time, immediately stopping further automation.

### 9.4 What this does NOT mean

This spec does not require any RevocationAgent to exist. It documents the pattern; it does not build the agent. Building specific RevocationAgents — whether by the OP/AT team, by third parties, or by individual principals running their own — is downstream of the protocol.

OP MUST NOT ship a built-in RevocationAgent or "automation" feature. Such features at the OP server level recreate the trust dependencies the decentralization posture exists to avoid. The RevocationAgent pattern is the answer for principals who want automation; OP-side automation is not.

## 10. Notification Responsibility

### 10.1 What this section covers

When revocation requires the principal's signature (a Sovereign principal who has not delegated to a RevocationAgent), AT MUST notify the principal that their action is required. This applies to:

- A status list update is needed because a credential's expiry has triggered.
- A credential the principal issued has been challenged or flagged.
- A scheduled revocation event is pending the principal's signature.

### 10.2 What this section does not cover

The specific notification mechanics — channels (email, push, Sovereign inbox), content (what the message says), timing (immediate, batched, daily digest), retry behavior — are user-facing UX concerns and belong in the Sovereign UI spec (Spec 3.7). This spec specifies architecturally that AT MUST notify; it does not specify how.

OP MUST NOT notify. OP serves bytes and exposes APIs. Notification is an AT responsibility because notification requires user-facing infrastructure (delivery channels, user preferences, retry queues) that does not belong in the protocol layer.

## 11. AT-Side Cache Invalidation

### 11.1 The problem

AT caches credentials in `partner_attestations` (per Spec 3.1) and `delegation_credentials` (per Spec 3.2). When a credential is revoked at its source, AT's cache is now stale — the cached credential reads as valid but the source status list says otherwise.

### 11.2 The solution

AT MUST re-check status when serving a cached credential for transaction-decision purposes. The check follows the existing `last_verified_at` pattern from Spec 3.1 §9.3 and Spec 3.2's caching, extended to status:

- Re-check status if `last_verified_at` is older than 24 hours AND the credential is being used for a transaction decision.
- For high-stakes transactions (counterparty policy-driven), re-check status at the time of the decision regardless of cache age.
- For display-only purposes (rendering a dashboard), serving the cached value without status re-check is acceptable; the UI MAY indicate the credential's status was last verified at `last_verified_at`.

When re-check reveals a credential has been revoked, AT MUST update `last_verified_at` to the current time AND MUST set a new column `revoked_at` to the time the revocation was detected. Future reads of this credential return revoked status without re-checking.

### 11.3 Schema additions

Both `partner_attestations` and `delegation_credentials` need a `revoked_at` column added:

```sql
-- Migration 005_add_revocation_tracking.py

ALTER TABLE partner_attestations
  ADD COLUMN revoked_at TIMESTAMPTZ,
  ADD COLUMN suspended_at TIMESTAMPTZ;

ALTER TABLE delegation_credentials
  ADD COLUMN revoked_at TIMESTAMPTZ,
  ADD COLUMN suspended_at TIMESTAMPTZ;

CREATE INDEX idx_partner_attestations_revoked  ON partner_attestations(revoked_at) WHERE revoked_at IS NOT NULL;
CREATE INDEX idx_delegations_revoked            ON delegation_credentials(revoked_at) WHERE revoked_at IS NOT NULL;
```

`suspended_at` is set when a suspension is detected and cleared when a subsequent re-check shows the suspension was lifted. `revoked_at` is set once and never cleared (revocation is terminal).

## 12. Database Schema for OP-Hosted Status Lists

### 12.1 The `vac_revocation_registry` table

Leo confirmed in C3 that this table becomes the OP-side state for Tier 3 status lists. The existing schema is incomplete; replacement is needed.

```sql
-- Migration 006_replace_vac_revocation_registry_for_status_lists.py

DROP TABLE IF EXISTS vac_revocation_registry;

CREATE TABLE vac_revocation_registry (
  id                       SERIAL PRIMARY KEY,
  status_list_id           TEXT UNIQUE NOT NULL,           -- the status list's URL identifier
  status_list_url          TEXT UNIQUE NOT NULL,           -- the public URL where the list is served
  owner_did                TEXT NOT NULL,                  -- the DID authorized to update this list
  status_purpose           TEXT NOT NULL,                  -- 'revocation' | 'suspension'
  current_bitstring        TEXT NOT NULL,                  -- compressed bitstring (base64-encoded)
  current_credential_jsonld JSONB NOT NULL,                -- the current signed BitstringStatusListCredential
  next_available_index     INTEGER NOT NULL DEFAULT 0,     -- next unallocated index
  total_capacity           INTEGER NOT NULL DEFAULT 131072, -- size of the bitstring
  created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_revocation_registry_owner   ON vac_revocation_registry(owner_did);
CREATE INDEX idx_revocation_registry_purpose ON vac_revocation_registry(status_purpose);
```

The `current_credential_jsonld` column holds the full signed `BitstringStatusListCredential` so that retrieval is a single read. When the Issuer submits an update, OP validates the submission, replaces this column with the new value, and updates `last_updated_at`. The previous version is not retained (status lists are not historical records; they are current-state).

### 12.2 Index allocation

The `next_available_index` column tracks which integer to assign to the next credential. When an Issuer requests an allocation via the API (§13.2), OP returns the current value and increments. This is an atomic operation; concurrent requests are serialized at the database level.

When `next_available_index` reaches `total_capacity`, OP refuses further allocations on this list and the Issuer must request a new list. Most Issuers will live within a single 131,072-entry list indefinitely.

## 13. API Endpoints

### 13.1 Status list retrieval (unauthenticated)

```
GET https://api.observerprotocol.org/sovereign/status-lists/<list-id>
```

Returns the current `BitstringStatusListCredential` JSON. Standard HTTP caching headers apply. This is the URL referenced in `credentialStatus.statusListCredential` for OP-hosted status lists.

### 13.2 Status list allocation (authenticated)

```
POST https://api.observerprotocol.org/sovereign/status-lists
```

Authenticated as the requesting Issuer's DID. Body specifies the `statusPurpose`. Response includes the new `list_id` and the `status_list_url` for use in credential `credentialStatus` fields.

```
POST https://api.observerprotocol.org/sovereign/status-lists/<list-id>/allocate-index
```

Authenticated as the list's owner DID. Returns the next available index. Atomic increment.

### 13.3 Status list update (authenticated)

```
POST https://api.observerprotocol.org/sovereign/status-lists/<list-id>
Content-Type: application/json

{ "credential": { ... full signed BitstringStatusListCredential ... } }
```

Authenticated as a DID with revocation authority over at least the credentials whose bits are changing (per §6.3). OP validates:

1. The submitted credential is a valid Bitstring Status List v1.0 structure.
2. The signature is valid for the signing DID.
3. The signing DID has revocation authority for every credential whose bit changed from 0 to 1. For changes from 1 to 0 (suspension lifts), authority is the same.
4. No bits were changed from 1 to 0 for `statusPurpose: "revocation"` (revocation is terminal; un-revocation is forbidden).

If all checks pass, OP serves the new credential at the canonical URL.

### 13.4 Status check (convenience, unauthenticated)

```
POST https://api.observerprotocol.org/verify/status
Content-Type: application/json

{ "credential": { ... full credential VC including credentialStatus ... } }
```

Response:

```json
{
  "credential_id": "...",
  "status_checks": [
    {
      "status_purpose": "revocation",
      "status_list_url": "...",
      "status_list_index": 42,
      "current_value": 0,
      "valid_for_purpose": true
    }
  ],
  "overall_valid": true
}
```

Convenience endpoint per Build Principles §6.3. High-stakes verification SHOULD be performed by the counterparty directly to avoid the network dependency.

## 14. Implementation Order

Recommended sequence for Maxi:

1. Run migration `006_replace_vac_revocation_registry_for_status_lists.py`. The status list infrastructure has nowhere to store state until this lands.
2. Implement Bitstring Status List v1.0 encode/decode/verify utilities. Standard W3C spec; reference implementations exist in JavaScript and Python that can be ported.
3. Implement the status list retrieval endpoint (§13.1). Read-only, simplest piece, validates the storage layer is working.
4. Implement status list allocation endpoints (§13.2). Atomic index allocation is the only subtle part.
5. Implement the status list update endpoint (§13.3) including the revocation authority verification (§6.3). This is the most complex piece because it requires walking delegation chains to verify authority.
6. Implement the status check convenience endpoint (§13.4).
7. Bump schemas to v2 with `credentialStatus` required (§4.3). Update issuance pipelines to issue against v2 schemas.
8. Run migration `005_add_revocation_tracking.py` to add cache-invalidation columns.
9. Update AT cache logic (§11) to re-check status on cached credentials per the policy.
10. Write negative tests: unauthorized status list updates reject, attempts to un-revoke reject, attempts to flip bits for credentials outside authority scope reject, malformed status list submissions reject.

Each step is a standalone milestone. Steps 1–6 can be tested with mocked credentials (no need for 3.1 or 3.2 to be deployed); steps 7–9 integrate with the live attestation and delegation pipelines and require coordination with their state.

Surface blockers at each step per Build Principles §5.3.

## 15. Testing Expectations

Per Build Principles §6.6. Specifically for 3.3:

- **Unit tests:** Bitstring encode/decode round-trip. Status list signature verification. Index allocation atomicity (concurrent requests serialize correctly). Authority check correctness (issuer authority, ancestor authority, ACL authority all verified independently).
- **Integration tests:** Full revocation lifecycle: issue credential, allocate index, embed `credentialStatus`, revoke, verify counterparty sees revoked status. Suspension cycle: issue, suspend, verify rejected, un-suspend, verify accepted again. Cascade verification: revoke parent delegation, verify descendant chain rejects without descendant being explicitly revoked.
- **Negative tests:** Attempt to un-revoke (must reject). Attempt to update status list with wrong-DID signature (must reject). Attempt to flip bits for credentials outside authority (must reject). Malformed submissions (wrong VC structure, invalid bitstring encoding) must reject. Status list update from a DID whose delegation has itself been revoked (must reject).
- **Decentralization conformance test:** Status list verification succeeds with OP unreachable (verifier has cached the status list within its TTL, walks the bitstring locally).
- **Mid-transaction tests:** Race condition between revocation and transaction broadcast. Race condition between revocation and rail confirmation. Verify behavior matches §8.1 in each case.
- **RevocationAgent pattern test:** Issue a delegation from a principal to an agent authorizing status list signing. Have the agent submit a status list update. Verify OP accepts it because the chain establishes authority. Revoke the principal-to-agent delegation. Have the agent submit again. Verify OP rejects because authority is now invalid.

## 16. Implementation Notes

### 16.1 Bitstring encoding details

The Bitstring Status List spec specifies GZIP-compressed, base64-encoded bitstrings. Implementations MUST follow this exact encoding chain (raw bitstring → GZIP → base64). Variations (different compression, different encoding) break interoperability with other Bitstring Status List implementations.

### 16.2 Reference libraries

- JavaScript: `@digitalbazaar/vc-bitstring-status-list` is the reference implementation.
- Python: `vc-bitstring-status-list` packages exist; verify against the spec before adopting.
- Rust: Hyperledger AnonCreds and similar projects have implementations.

Maxi should evaluate whether to adopt a reference library or implement from scratch. The encode/decode logic is small (~200 lines); the spec compliance edge cases (specifically around bitstring length and indexing semantics) make a tested library appealing.

### 16.3 Operational considerations

- **List size monitoring.** OP should track per-list utilization (`next_available_index / total_capacity`). When a list exceeds 90% capacity, the owner DID should be notified to provision a second list.
- **Status list versioning.** The `last_updated_at` timestamp is the de-facto version. Verifiers cache status lists per HTTP headers; OP should set sensible `Cache-Control` and `Last-Modified` headers to support efficient verifier behavior.
- **Backups.** The `current_credential_jsonld` column holds critical state (the signed status list). Standard PostgreSQL backup procedures apply.

## 17. Next Steps

1. `BitstringStatusListCredential` JSON Schema (this is W3C-defined; reference rather than republish).
2. Updated v2 schemas for attestation and delegation credentials with `credentialStatus` as required, drafted as companion artifacts.
3. Maxi begins implementation in the order specified in §14.
4. Spec 3.4 (Attestation Requests / pull-side flow) drafted next.

---

*This spec is written against Build Principles v0.2. If that document changes, this spec may need review.*
