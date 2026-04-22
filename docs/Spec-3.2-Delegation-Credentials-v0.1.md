# Spec 3.2 — Delegation Credentials (Recursive DID-to-DID Primitive)
**Phase:** 3
**Capability:** 2 of 8
**Version:** 0.1
**Date:** April 21, 2026
**Authors:** Boyd Cohen, Claude
**Status:** Ready for implementation
**References:** OP/AT Build Principles v0.2, Spec 3.1 (Third-Party Attestations)

---

## 1. Purpose

This spec defines the delegation primitive: how one DID cryptographically authorizes another DID to take actions and/or issue further delegations, and how verifiers compute the effective authority of any subject by walking the resulting graph.

Delegation in AIP is recursive. An "organization delegating to an agent" is a chain of individual DID-to-DID delegations, not a distinct credential type. A "human authorizing their personal agent" is the same primitive with a chain length of one. Every delegation is an edge in a directed graph of authority assertions.

This spec subsumes what earlier drafts split between "Delegation Credentials" and "Delegation Chains" — the two are not separable in the recursive model.

## 2. Scope

### In scope

- The single-edge delegation primitive (one DID delegates to another)
- Structured action scope (what the subject may transact)
- Structured delegation scope (what further delegations the subject may issue)
- ACL declarations for modification and revocation authority
- Multi-edge graph verification and scope attenuation at every link
- Emergent depth (no configured maximum; terminates when a delegation declares no-further-delegation)
- `enforcementMode` declaration per edge
- W3C VC schema for the delegation primitive
- Database schema for storing delegations in AT
- Verification endpoint for delegation graphs

### Out of scope

- Revocation mechanism and status list infrastructure (Spec 3.3)
- Protocol-level enforcement implementation (OWS integration, AT pre-transaction check wiring) (Spec 3.5)
- Sovereign UI for issuing delegations (Spec 3.7)
- Enterprise dashboard for delegation management (Spec 3.8)

### Dependencies

- DID resolution endpoint live (Phase 2, complete).
- Ed25519 signing infrastructure operational (Phase 2, complete).
- `delegation_credentials` table exists in `agentic_terminal_db` (exists; schema replacement required).
- Attestation verification endpoint from Spec 3.1 provides verification pattern this spec follows.

## 3. Conceptual Model

### 3.1 Delegation as a graph edge

Every delegation is a directed edge in a graph where nodes are DIDs and edges are signed authority assertions. An edge from DID-A to DID-B carries:

- **Action scope:** what DID-B may do (transact on which rails, up to what value, with which counterparty types, etc.).
- **Delegation scope:** what further delegations DID-B may issue (to whom, with what maximum action scope, whether recipients may themselves delegate further).
- **ACL:** who has authority to modify or revoke this specific edge.
- **Temporal bounds:** `validFrom` and `validUntil`.
- **Enforcement declaration:** how the action scope is enforced when DID-B transacts.
- **Parent reference:** the edge upstream of this one in the graph (null for root delegations).
- **Issuer signature:** cryptographic proof that DID-A (the issuer) created this edge.

A subject's effective authority is computed by walking the graph backward from the subject to a trust root the verifier accepts, verifying every edge along the way. If any edge in the path is invalid (signature fails, expired, revoked, violates attenuation), the subject has no effective authority derived through that path.

### 3.2 No type hierarchy

There is one credential type: `DelegationCredential`. There is no `OrganizationalDelegationCredential`, no `PrincipalAuthorizationCredential`, no `DepartmentalDelegationCredential`. Usage patterns ("this is a principal authorizing their agent," "this is a CFO authorizing a team") are interpretive labels applied to delegation graphs with particular shapes. They are not type distinctions encoded in the credential.

The practical implication: a verifier processing a delegation does not branch on "is this an org delegation or a principal delegation?" It processes the same primitive regardless of whether the issuer DID is controlled by an individual, an organization, a department, or an agent.

### 3.3 Scope attenuation is intrinsic

Every child delegation's scope MUST be a subset of its parent's scope, for both action scope and delegation scope. Attenuation is enforced at verification time by walking the chain and checking at each edge. Verifiers MUST NOT trust an edge's declared scope without verifying that its parent authorized that scope.

This means: a delegation graph is self-auditing. A verifier with the leaf credential and the ability to resolve parent references can independently verify that no edge exceeds the authority it was granted.

### 3.4 Depth is emergent

There is no configured `max_delegation_depth`. Whether a delegation may have children is expressed in the delegation scope: specifically, whether the scope grants the subject authority to issue further delegations, and if so, what maximum scope those children may carry.

A delegation whose delegation scope is "none" (the subject may not issue further delegations) terminates the chain at that point. A chain is as deep as the recursive "may delegate further" declarations allow. In practice most chains will be 1–3 edges deep; the protocol permits more but verifiers MAY apply policy limits.

## 4. Credential Structure

### 4.1 Canonical schema

Every delegation credential follows this structure:

```json
{
  "@context": [
    "https://www.w3.org/ns/credentials/v2",
    "https://observerprotocol.org/contexts/delegation/v1"
  ],
  "id": "https://<issuer-domain>/delegations/<credential-id>",
  "type": ["VerifiableCredential", "DelegationCredential"],
  "issuer": "<issuer DID>",
  "validFrom": "<ISO 8601 timestamp>",
  "validUntil": "<ISO 8601 timestamp>",
  "credentialSubject": {
    "id": "<subject DID>",
    "actionScope": {
      "allowed_rails": ["<rail-id>", "..."],
      "allowed_counterparty_types": ["<type-from-registry>", "..."],
      "per_transaction_ceiling": { "amount": "<decimal>", "currency": "<ISO-4217>" },
      "cumulative_ceiling": { "amount": "<decimal>", "currency": "<ISO-4217>", "period": "<ISO-8601-duration>" },
      "geographic_restriction": { "allowed": ["<ISO-3166>"], "disallowed": ["<ISO-3166>"] },
      "allowed_merchant_categories": ["<MCC-or-equivalent>", "..."]
    },
    "delegationScope": {
      "may_delegate_further": <boolean>,
      "max_child_action_scope": { "<subset of actionScope structure>" },
      "may_delegate_delegation_authority": <boolean>,
      "allowed_child_subject_types": ["<type-from-registry>", "..."]
    },
    "acl": {
      "revocation_authority": ["<DID>", "..."],
      "modification_authority": ["<DID>", "..."]
    },
    "enforcementMode": "<protocol_native | pre_transaction_check>",
    "parentDelegationId": "<URL of parent delegation, or null for root>",
    "kybCredentialId": "<URL of KYB VC backing this delegation, or null>"
  },
  "credentialSchema": {
    "id": "https://observerprotocol.org/schemas/delegation/v1.json",
    "type": "JsonSchema"
  },
  "proof": {
    "type": "Ed25519Signature2020",
    "created": "<ISO 8601 timestamp>",
    "verificationMethod": "<issuer DID>#<key-id>",
    "proofPurpose": "assertionMethod",
    "proofValue": "<base58btc-encoded signature>"
  }
}
```

The absence of a `credentialStatus` field is deliberate. Spec 3.3 adds revocation via status list; delegations issued before 3.3 ships are in the transitional state described in Spec 3.1 §4.1.

### 4.2 Action scope

The `actionScope` field defines what the subject may transact. All fields within it are optional; absence of a field means "no restriction on this dimension" (but always bounded by the parent's action scope).

- `allowed_rails` — list of rail identifiers. Values match rail names used in OP (`tron`, `lightning`, `x402`, `trc20`, etc.). Absence means all rails supported by the issuer.
- `allowed_counterparty_types` — from Type Registry (§7.1). Absence means no restriction.
- `per_transaction_ceiling` — hard maximum per individual transaction. Currency in ISO 4217. Absence means no per-transaction ceiling.
- `cumulative_ceiling` — maximum cumulative value over a period (ISO 8601 duration; e.g., `P30D` for 30 days). Absence means no cumulative ceiling.
- `geographic_restriction` — allow-list and/or deny-list of jurisdictions (ISO 3166 country codes). Absence means no restriction.
- `allowed_merchant_categories` — MCC codes or equivalent. Absence means no restriction.

### 4.3 Delegation scope

The `delegationScope` field defines what further delegations the subject may issue.

- `may_delegate_further` — boolean. If `false`, the subject may not issue any child delegations. Terminates the chain at this edge.
- `max_child_action_scope` — the maximum action scope that any child delegation may carry. Structurally identical to `actionScope`. Child action scopes MUST be subsets of this.
- `may_delegate_delegation_authority` — boolean. If `false`, children may have non-empty action scope but MUST have `may_delegate_further: false` — i.e., grandchildren are forbidden. If `true`, children may themselves authorize further delegations.
- `allowed_child_subject_types` — optional list constraining who the subject may delegate to. Values from Type Registry (§7.1). Default (absent) means no restriction.

A delegation with `may_delegate_further: false` and empty `delegationScope` makes the subject a terminal node — they can act under the action scope but cannot grant authority to anyone else. This is the common Sovereign pattern (human → their own agent, agent is a terminal node).

### 4.4 ACL

The `acl` field declares who has authority over the specific delegation edge.

- `revocation_authority` — list of DIDs authorized to revoke this edge. The issuer DID is implicitly authorized and need not be listed (but MAY be listed for clarity). Parent-chain issuers (ancestors) are implicitly authorized via the ACL-on-chain principle from Build Principles §7 (Capability 3) and need not be listed.
- `modification_authority` — list of DIDs authorized to modify this edge. Since delegations are immutable once issued (modification requires revoke-and-reissue), this field's practical effect in current phase is governing who may re-issue a replacement. Reserved for future use; currently informational.

ACL declarations are additive to the implicit authorities described in Build Principles §7. An explicit empty list means "only the implicit authorities (issuer + ancestors)." An explicit non-empty list grants authority to additional parties beyond the implicit set.

### 4.5 Enforcement mode

The `enforcementMode` field declares how the delegation's action scope is enforced at transaction time. Values:

- `protocol_native` — enforced by the rail itself. The subject cannot transact outside scope even if they try, because the rail refuses.
- `pre_transaction_check` — enforced by AT or an equivalent pre-transaction gateway before the transaction reaches the rail. Requires the transaction flow to pass through a gateway that consults the delegation.

The issuer declares this value. Counterparties MAY reject delegations whose `enforcementMode` does not meet their policy (e.g., a counterparty requiring `protocol_native` for high-value transactions).

Specific rail ↔ enforcement mapping is left to Spec 3.5; this spec only declares the field exists and what values are permitted.

### 4.6 Parent reference

`parentDelegationId` is the URL of the parent delegation in the chain, or `null` for root delegations. Roots are delegations issued by trust anchors the verifier accepts directly (e.g., a human's own DID delegating to their own agent — root with the human as trust anchor).

The URL MUST resolve to the parent credential's JSON. Verifiers fetch the parent via this URL and verify recursively.

### 4.7 KYB credential link

`kybCredentialId` is optional. When present, it points at a KYB attestation (from Spec 3.1) backing the issuer of this delegation. Useful for organizational contexts where the issuer is a corporate DID whose real-world identity has been verified by a KYB provider.

Required: no. A delegation without a KYB link is structurally valid. Counterparties may apply their own policy — e.g., "accept only delegations whose root issuer has a valid KYB credential" — but the protocol does not mandate it.

## 5. Verification

### 5.1 Single-edge verification

Given a delegation credential, verification proceeds:

1. Resolve the issuer DID and extract the verification method referenced in `proof.verificationMethod`.
2. Verify the Ed25519 signature over the canonicalized VC (with `proofValue` removed).
3. Validate the full VC JSON against the schema at `credentialSchema.id`.
4. Check temporal validity: current time within `[validFrom, validUntil]`.
5. Check the status list (once Spec 3.3 lands; until then, delegations are unrevokable within their validity window).

A failure at any step invalidates the edge.

### 5.2 Graph verification

When the delegation has a non-null `parentDelegationId`, verification extends:

6. Fetch the parent credential from `parentDelegationId`.
7. Recursively verify the parent per §5.1 and §5.2.
8. Verify attenuation: the child's `actionScope` MUST be a subset of the parent's `delegationScope.max_child_action_scope`, AND the child's `delegationScope.max_child_action_scope` MUST be a subset of the parent's `delegationScope.max_child_action_scope`.
9. Verify delegation permission: the parent's `delegationScope.may_delegate_further` MUST be `true`. If the child itself declares `may_delegate_further: true`, the parent's `delegationScope.may_delegate_delegation_authority` MUST also be `true`.
10. Verify subject type: if the parent's `delegationScope.allowed_child_subject_types` is present, the child's subject MUST match one of the listed types.
11. Verify temporal consistency: the child's `validUntil` MUST be ≤ the parent's `validUntil`.

### 5.3 Attenuation algorithm

For each field in `actionScope` and `delegationScope.max_child_action_scope`, the child's value MUST NOT exceed the parent's. Specific rules per field type:

- **List-valued fields** (`allowed_rails`, `allowed_counterparty_types`, `allowed_merchant_categories`, `allowed_child_subject_types`): child's list MUST be a subset of parent's list. Child absence means "inherit parent's list"; child presence with a non-subset list is a violation.
- **Numeric ceilings** (`per_transaction_ceiling`, `cumulative_ceiling`): child's amount MUST be ≤ parent's amount. Currency MUST match. For `cumulative_ceiling`, child's period MUST be ≤ parent's period (shorter windows are more restrictive and therefore attenuated).
- **Geographic restriction**: child's allow-list MUST be a subset of parent's allow-list; child's deny-list MUST be a superset of parent's deny-list. In other words, the child may be more restrictive, never less.
- **Boolean permissions** (`may_delegate_further`, `may_delegate_delegation_authority`): child's `true` requires parent's `true`. Child's `false` is always permitted.

Any violation at any edge invalidates the entire chain from that point down.

### 5.4 Trust root

A delegation chain terminates at a root (a delegation with `parentDelegationId: null`). The verifier MUST determine whether to accept the root's issuer as a trust anchor. Acceptable trust anchors are verifier-policy, not protocol-mandated. Common anchors:

- A human's own DID, verifying their own authorization over their own agent (Sovereign pattern).
- An organization's root DID, backed by a KYB attestation the verifier trusts.
- A named institutional DID the verifier has pre-approved.

The protocol provides the cryptographic primitives; the trust decision is the verifier's.

### 5.5 Graph cycles

Delegation graphs MUST NOT contain cycles. A cycle means DID-A delegates to DID-B which (directly or transitively) delegates back to DID-A. Cycles are detected by maintaining a set of visited issuer DIDs during graph traversal; encountering an already-visited issuer is a cycle.

Verifiers MUST detect cycles and reject chains containing them. Issuers SHOULD refuse to sign a delegation that would create a cycle (though this is a client-side check and cannot be enforced at the protocol level without full-graph visibility).

### 5.6 Offline verification

The graph verification algorithm above works offline if the verifier has cached all relevant DIDs, schemas, and delegation credentials. OP's DID resolver and schema hosting are used for preparation, not for real-time verification. This matches the decentralization conformance property from Build Principles §2.4.

## 6. Hosting

### 6.1 Issuer-hosted (Tier 2, default)

Delegations default to Tier 2 hosting. The issuer hosts the credential at the URL in its `id` field. Children reference parents via `parentDelegationId` — this creates an HTTP-resolvable chain.

### 6.2 OP-hosted (Tier 3)

Individual principals issuing delegations from Sovereign use Tier 3 hosting. The principal signs the delegation client-side with their key; OP hosts the resulting JSON at a URL under OP's control. The principal's DID (`did:web:agenticterminal.io:sovereign:<handle>`) remains the issuer; OP serves the bytes but does not sign.

Sovereign principals do not have their own hosting infrastructure, so Tier 3 is the only practical option for them. Enterprise issuers with their own infrastructure use Tier 2.

### 6.3 Hosting URL conventions

- Tier 2: issuer-chosen URL under issuer's domain, pattern typically `https://<issuer-domain>/delegations/<id>`.
- Tier 3 (Sovereign): `https://api.observerprotocol.org/sovereign/delegations/<issuer-handle>/<id>`.

Counterparties resolve whichever URL appears in the credential's `id` field; both patterns work identically from the verifier's perspective.

## 7. Type Registry Entries (Added by This Spec)

### 7.1 `allowed_counterparty_types`

This registry was established in Build Principles references and appeared in prior AIP drafts. Spec 3.2 canonicalizes it:

| Value | Description |
|---|---|
| `verified_merchant` | Counterparty is a registered merchant with a verified business identity |
| `kyb_verified_org` | Counterparty is an organization with a valid KYB attestation |
| `did_verified_agent` | Counterparty is an agent with a resolvable DID |
| `delegated_agent` | Counterparty holds a valid, non-expired delegation |
| `individual` | Counterparty is an individual principal |
| `unverified` | No counterparty verification required |

Applies to `actionScope.allowed_counterparty_types` and `delegationScope.allowed_child_subject_types`.

### 7.2 `enforcementMode`

| Value | Description |
|---|---|
| `protocol_native` | Enforced by the rail itself (e.g., OWS policy engine) |
| `pre_transaction_check` | Enforced by AT or equivalent gateway before reaching the rail |

New values may be added in future specs as additional enforcement modes are defined (smart-contract wallet enforcement for EVM chains is expected as Phase 4 extends this list).

### 7.3 Delegation-specific denial and revocation reasons

Added to the AIP Type Registry's denial and revocation reason enumerations:

- `no_delegation_credential` (denial) — no valid delegation found for the presenting subject.
- `delegation_credential_expired` (denial) — delegation present but past `validUntil`.
- `delegation_scope_violation` (denial) — transaction exceeds the delegation's action scope.
- `delegation_chain_invalid` (denial) — one or more edges in the chain fail verification.
- `delegation_chain_cycle` (denial) — cycle detected in the delegation graph.
- `enforcement_mode_insufficient` (denial) — counterparty policy requires a stricter enforcement mode than the presented delegation declares.
- `parent_delegation_revoked` (revocation cascade) — revocation propagates because a parent delegation in the chain was revoked.

## 8. Database Schema

### 8.1 The `delegation_credentials` table

The existing table was designed against the flat-delegation model and needs replacement. Since no production data has been written to it in a form compatible with the recursive model, the migration drops and recreates.

```sql
-- Migration 004_replace_delegation_credentials_for_recursive_model.py

DROP TABLE IF EXISTS delegation_credentials;

CREATE TABLE delegation_credentials (
  id                    SERIAL PRIMARY KEY,
  credential_id         TEXT UNIQUE NOT NULL,              -- the VC's id field (URL)
  issuer_did            TEXT NOT NULL,                      -- the issuer's DID
  subject_did           TEXT NOT NULL,                      -- the subject's DID
  credential_jsonld     JSONB NOT NULL,                     -- the full signed VC
  credential_url        TEXT NOT NULL,                      -- hosting URL (may equal credential_id)
  parent_delegation_id  TEXT,                               -- URL of parent delegation, null for roots
  valid_from            TIMESTAMPTZ NOT NULL,
  valid_until           TIMESTAMPTZ NOT NULL,
  enforcement_mode      TEXT NOT NULL,                      -- 'protocol_native' | 'pre_transaction_check'
  may_delegate_further  BOOLEAN NOT NULL,                   -- extracted from delegationScope for query optimization
  kyb_credential_id     TEXT,                               -- optional KYB link
  cached_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_verified_at      TIMESTAMPTZ
);

CREATE INDEX idx_delegations_issuer   ON delegation_credentials(issuer_did);
CREATE INDEX idx_delegations_subject  ON delegation_credentials(subject_did);
CREATE INDEX idx_delegations_parent   ON delegation_credentials(parent_delegation_id);
CREATE INDEX idx_delegations_validity ON delegation_credentials(valid_until);
```

The full VC is stored in `credential_jsonld`; frequently-queried fields are denormalized as columns for index efficiency. Graph traversal queries work by joining on `parent_delegation_id`.

### 8.2 Graph query support

A recursive CTE supports walking the chain from leaf to root:

```sql
WITH RECURSIVE delegation_chain AS (
  SELECT credential_id, issuer_did, subject_did, parent_delegation_id, 1 AS depth
  FROM delegation_credentials
  WHERE credential_id = <leaf-credential-id>
  UNION ALL
  SELECT d.credential_id, d.issuer_did, d.subject_did, d.parent_delegation_id, dc.depth + 1
  FROM delegation_credentials d
  JOIN delegation_chain dc ON d.credential_id = dc.parent_delegation_id
)
SELECT * FROM delegation_chain ORDER BY depth;
```

This pattern is used by the verification endpoint when a caller requests the full chain for a given delegation.

## 9. API Endpoints

### 9.1 Delegation verification endpoint

```
POST https://api.observerprotocol.org/verify/delegation
Content-Type: application/json

{
  "credential": { ... full delegation VC JSON ... },
  "resolve_chain": true
}
```

Response:

```json
{
  "verified": true,
  "checks": {
    "signature": "pass",
    "schema": "pass",
    "validity_period": "pass",
    "issuer_did_resolvable": "pass",
    "attenuation": "pass",
    "no_cycles": "pass",
    "chain_complete": "pass"
  },
  "chain": [
    { "credential_id": "...", "issuer_did": "...", "subject_did": "..." },
    "..."
  ],
  "effective_action_scope": { ... the attenuated action scope at the leaf ... }
}
```

When `resolve_chain` is `true`, the endpoint fetches the parent chain and verifies every edge. When `false`, only the single edge is verified.

Convenience endpoint per Build Principles §6.3. High-stakes verification SHOULD be performed by the counterparty directly.

### 9.2 Sovereign delegation hosting endpoint

```
POST https://api.observerprotocol.org/sovereign/delegations
Content-Type: application/json

{ "credential": { ... signed VC JSON ... } }
```

Authenticated as the Sovereign principal via the existing DID-auth flow. The endpoint validates the submitted VC (signature matches the authenticated principal's DID, schema valid, etc.) and hosts it at `https://api.observerprotocol.org/sovereign/delegations/<issuer-handle>/<id>`. Returns the hosting URL.

OP stores the bytes; the principal signed them. Tier 3 hosting per Build Principles §2.3.

### 9.3 Delegation retrieval

```
GET https://api.observerprotocol.org/sovereign/delegations/<issuer-handle>/<id>
```

Unauthenticated. Returns the VC JSON. Used by counterparties resolving parent references that point at Sovereign-hosted delegations.

## 10. Implementation Order

Recommended sequence for Maxi:

1. Publish `https://observerprotocol.org/schemas/delegation/v1.json` via observer-protocol-website repo.
2. Run migration `004_replace_delegation_credentials_for_recursive_model.py` against `agentic_terminal_db`.
3. Implement single-edge verification (§5.1). Adapt the attestation verification pattern from Spec 3.1.
4. Implement graph traversal and attenuation (§5.2, §5.3, §5.5). This is the most intricate piece — allocate time for attenuation edge cases.
5. Implement the verification endpoint (§9.1).
6. Implement Sovereign hosting endpoints (§9.2, §9.3).
7. Implement retrieval and chain query support (§8.2).
8. Write negative tests exhaustively — attenuation violations, cycles, expired parents, missing parents, unresolvable issuer DIDs, enforcement-mode mismatches.

Each step is a standalone milestone. Surface blockers at each step per Build Principles §5.3.

## 11. Testing Expectations

Per Build Principles §6.6. Specifically for 3.2:

- **Unit tests:** Single-edge verification. Attenuation algorithm on each field type (list subsets, numeric ceilings, geographic logic, boolean permissions). Cycle detection.
- **Integration tests:** Multi-edge chain verification (depth 2, 3, 5). Sovereign-hosted root with enterprise-hosted children and vice versa. Cross-hosting-tier chains (mix of Tier 2 and Tier 3 URLs in one chain).
- **Negative tests:** Chain with broken attenuation at each possible link. Chain with cycle. Chain with expired parent. Chain with unresolvable parent URL. Chain where a middle edge's signature fails. Chain where `may_delegate_further: false` is violated by a child's existence. Chain where `allowed_child_subject_types` is violated.
- **Decentralization conformance test:** Full chain verification with OP API unreachable, using only cached credentials and DID documents.
- **Sovereign end-to-end test:** A Sovereign principal issues a delegation to an agent DID they control, the delegation is hosted via OP, a counterparty fetches and verifies without the principal being online.

## 12. Implementation Notes on the Consumer-Authorization Pattern

While `PrincipalAuthorizationCredential` is not a distinct type, the consumer-e-commerce authorization pattern is an expected high-volume usage of this primitive. Implementers should ensure the primitive works well for this case:

- **Principal issuer:** `did:web:agenticterminal.io:sovereign:<handle>`.
- **Subject:** the principal's own agent DID.
- **Action scope:** typically includes `per_transaction_ceiling`, `cumulative_ceiling` with short period (`P30D` common), `allowed_merchant_categories` if the principal wants to restrict.
- **Delegation scope:** `may_delegate_further: false`. The agent is terminal.
- **Enforcement mode:** typically `pre_transaction_check` for consumer rails; `protocol_native` where OWS is integrated.
- **Parent:** `null`. Principal is the trust root.
- **KYB link:** `null`. Individuals do not have KYB.
- **Hosting:** Tier 3 (OP-hosted, principal-signed).

A Sovereign UI building on top of this primitive surfaces only the semantic meaning ("authorize your agent to spend up to $X at merchant categories Y until date Z") without exposing the primitive's full structure. The full structure is available to any counterparty that needs it.

## 13. Next Steps

1. `delegation/v1.json` JSON Schema drafted as a companion artifact.
2. Maxi begins implementation in the order specified in §10.
3. Spec 3.3 (Revocation and Lifecycle) drafted next, after Leo's C3 review is fully consolidated. 3.3 will add the `credentialStatus` field to both attestations (Spec 3.1) and delegations (this spec).

---

*This spec is written against Build Principles v0.2. If that document changes, this spec may need review.*
