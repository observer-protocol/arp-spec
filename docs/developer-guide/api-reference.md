# API Reference

Base URL: `https://api.observerprotocol.org`

Interactive API explorer: `https://api.observerprotocol.org/docs`

## Authentication

Most identity and credential endpoints are public (no auth required). Chain verification, audit, and extension endpoints require an integrator API key:

```
Authorization: Bearer <api_key>
```

## Identity & Registration

### Register Agent

```
POST /observer/register-agent
```

Register a new agent with an Ed25519 public key.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `public_key` | string | Yes | Ed25519 public key (hex-encoded) |
| `agent_name` | string | No | Human-readable name |
| `alias` | string | No | Short alias |
| `framework` | string | No | Agent framework identifier |

**Response (201):**
```json
{
  "agent_id": "d13cdfce...",
  "agent_did": "did:web:observerprotocol.org:agents:d13cdfce...",
  "agent_name": "My Agent",
  "verification_status": "registered",
  "did_document": { ... },
  "next_steps": ["Complete challenge-response verification"]
}
```

### Generate Challenge

```
POST /observer/challenge?agent_id={agent_id}
```

Generate a cryptographic challenge for key ownership verification.

**Response (200):**
```json
{
  "challenge_id": "ch_abc123",
  "nonce": "a1b2c3d4e5f6...",
  "expires_at": "2026-04-25T15:05:00Z",
  "expires_in_seconds": 300
}
```

### Verify Agent

```
POST /observer/verify-agent?agent_id={agent_id}&signed_challenge={signature_hex}
```

Submit a signed challenge to prove key ownership. Challenge must be signed with the agent's Ed25519 private key.

**Response (200):**
```json
{
  "verified": true,
  "agent_id": "d13cdfce...",
  "verification_method": "challenge_response_ed25519"
}
```

### Get Agent Profile

```
GET /api/v1/agents/{agent_id}/profile
```

Public agent profile with trust data.

**Response (200):**
```json
{
  "agent_id": "d13cdfce...",
  "agent_name": "Maxi",
  "did": "did:web:observerprotocol.org:agents:d13cdfce...",
  "verified": true,
  "trust_score": 78,
  "transaction_count": 47,
  "attestation_count": 3,
  "rails": ["lightning", "tron"],
  "view_context": "public"
}
```

### Resolve DID Document

```
GET /agents/{agent_id}/did.json
```

W3C DID document for the agent. Publicly resolvable.

### Key Rotation

```
PUT /agents/{agent_id}/keys
```

Rotate an agent's signing key.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `new_public_key` | string | Yes | New Ed25519 public key (hex) |
| `signature` | string | No | Signature proving ownership of old key |

---

## Credentials

### Get VAC

```
GET /vac/{agent_id}
```

Retrieve the agent's Verified Agent Credential (W3C Verifiable Presentation).

### Get Attestations

```
GET /vac/{agent_id}/attestations
```

All partner attestations for an agent. Public endpoint.

| Param | Type | Description |
|-------|------|-------------|
| `partner_type` | string | Filter: `corpo`, `verifier`, `counterparty`, `infrastructure` |

**Response (200):**
```json
{
  "agent_id": "d13cdfce...",
  "attestations": [
    {
      "attestation_id": "att_123",
      "partner_name": "MoonPay",
      "partner_type": "corpo",
      "claims": { "kyb_status": "verified" },
      "issued_at": "2026-04-10T00:00:00Z"
    }
  ],
  "count": 1
}
```

### Get VAC History

```
GET /vac/{agent_id}/history?limit=10
```

Previous VAC versions.

---

## Chain Verification

### Verify Transaction

```
POST /v1/chain/verify
Authorization: Bearer <api_key>
```

Chain-agnostic transaction verification. See [Chain Verification](./chain-verification.md) for full details.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `receipt_reference` | string | Yes | Unique ID (idempotency key) |
| `chain` | string | Yes | `lightning`, `tron`, or `stacks` |
| `transaction` | object | No | Amount, sender, recipient |
| `chain_specific` | object | Yes | Chain-specific verification params |

**Response (200):**
```json
{
  "verified": true,
  "receipt_reference": "urn:uuid:...",
  "chain": "lightning",
  "transaction_reference": "abc123...",
  "explorer_url": "https://...",
  "chain_specific": { ... },
  "idempotent_replay": false
}
```

**Errors:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `unsupported_chain` | Chain not supported |
| 401 | `unauthorized` | Invalid API key |
| 409 | `chain_mismatch` | Receipt already verified on a different chain |
| 422 | `verification_failed` | Chain verification failed |

---

## Audit Trail

### Write Verified Event

```
POST /v1/audit/verified-event
Authorization: Bearer <api_key>
```

Write a verified transaction to the audit trail. Surfaces in the AT Enterprise dashboard.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `receipt_reference` | string | Yes | Receipt UUID (idempotency key) |
| `agent` | object | Yes | `agent_id` and optional `did` |
| `transaction` | object | Yes | Amount, category, rail, counterparty |
| `settlement_reference` | object | No | Transaction hash, rail, settled_at |
| `verification` | object | No | Verdict, delegation_id, verified_at |

**Response (201):**
```json
{
  "status": "created",
  "event_id": "evt_abc123",
  "receipt_reference": "urn:uuid:...",
  "dashboard_url": "https://app.agenticterminal.io/dashboard/events/evt_abc123",
  "idempotent_replay": false
}
```

### Submit Agent Activity Credential

```
POST /audit/activity
```

Submit an agent-signed activity credential (W3C VC).

### Submit Counterparty Receipt

```
POST /audit/receipt
```

Submit a counterparty-signed receipt credential.

### Query Agent Activities

```
GET /audit/agent/{agent_did}/activities?limit=50&since=2026-04-01T00:00:00Z
```

### Query Audit Coverage

```
GET /audit/agent/{agent_did}/coverage?window=30
```

Returns receipt coverage rate for the agent over the specified window (days).

---

## Trust Score

### Get Trust Score

```
GET /api/v1/trust/score/{agent_id}
```

Composite trust score.

### Get Trust Score Breakdown

```
GET /api/v1/trust/tron/score/{agent_id}
```

Full breakdown with component scores. See [Trust Score](./trust-score.md).

---

## VAC Extensions

### Register Extension

```
POST /v1/vac/extensions/register
Authorization: Bearer <api_key>
```

Register a VAC extension schema. See [VAC Extensions](./vac-extensions.md).

### Submit Extension Attestation

```
POST /v1/vac/extensions/attest
Authorization: Bearer <api_key>
```

Submit a pre-signed extension attestation credential.

---

## TRON-Specific

### Submit TRON Receipt

```
POST /api/v1/tron/receipts/submit
```

Submit a signed `tron_receipt_v1` Verifiable Credential.

### Get TRON Receipts

```
GET /api/v1/tron/receipts/{agent_id}?limit=50&verified_only=true
```

### Get TRON Receipt Count

```
GET /api/v1/tron/receipts/{agent_id}/count
```

---

## Counterparties

### Get Agent Counterparties

```
GET /api/v1/agents/{agent_id}/counterparties?limit=50
```

Public view returns aggregate counts. Authenticated view returns per-counterparty detail.

---

## Error Codes

| Status | Meaning |
|--------|---------|
| 400 | Malformed request |
| 401 | Invalid or missing API key / session |
| 403 | Valid key but insufficient permissions |
| 404 | Resource not found |
| 409 | Conflict (idempotency key mismatch, chain mismatch) |
| 422 | Validation failed (verification failed, schema invalid) |
| 500 | Internal error (retry with backoff) |
