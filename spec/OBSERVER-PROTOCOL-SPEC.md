# VAC Specification v0.3.2
## Verified Agent Credential

**Status:** Draft  
**Version:** 0.3.2  
**Date:** 2026-03-27  
**License:** CC BY 4.0  
**Authors:** Observer Protocol contributors  
**Changelog:** See §12  

---

## Abstract

The Verified Agent Credential (VAC) is a cryptographically signed document that attests to an AI agent's verified economic activity and identity claims. VAC is part of the Observer Protocol (OP) and provides a standardized, privacy-preserving format for agents to prove their transaction history, counterparties, volume, and partner attestations.

VAC replaces and extends the Agent Reporting Protocol (ARP) with:
- Cryptographic signing by OP
- Partner attestation extensions
- Counterparty metadata hash anchoring
- Credential lifecycle management (refresh, revocation)

---

## 1. VAC Structure

A VAC credential is a JSON document with two main sections:
- **`core`**: OP-verified cryptographic facts (transactions, counterparties, volume, rails)
- **`extensions`**: Partner attestations + counterparty metadata hashes

### 1.1 Top-Level Fields

```json
{
  "version": "1.0.0",
  "issued_at": "2026-03-23T16:00:00Z",
  "expires_at": "2026-03-30T16:00:00Z",
  "credential_id": "vac_agent123abc_1a2b3c4d",
  "core": { ... },
  "extensions": { ... },
  "signature": "hex_encoded_signature"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | ✅ | VAC schema version (currently "1.0.0") |
| `issued_at` | string | ✅ | ISO 8601 timestamp of issuance |
| `expires_at` | string | ✅ | ISO 8601 timestamp of expiration (max 7 days) |
| `credential_id` | string | ✅ | Unique identifier for this credential |
| `core` | object | ✅ | Core VAC fields (see §1.2) |
| `extensions` | object | ❌ | Partner attestations and counterparty metadata |
| `signature` | string | ✅ | OP's cryptographic signature of the VAC payload |

### 1.2 Core Fields

```json
{
  "core": {
    "agent_id": "abc123def456",
    "total_transactions": 42,
    "total_volume_sats": 1500000,
    "unique_counterparty_count": 7,
    "rails_used": ["lightning", "L402", "x402"],
    "first_transaction_at": "2026-02-01T10:00:00Z",
    "last_transaction_at": "2026-03-22T14:30:00Z"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_id` | string | ✅ | The agent's unique identifier |
| `total_transactions` | integer | ✅ | Count of verified transactions |
| `total_volume_sats` | integer | ✅ | Total volume in satoshis |
| `unique_counterparty_count` | integer | ✅ | Number of unique counterparties |
| `rails_used` | array | ✅ | List of settlement protocols used |
| `first_transaction_at` | string | ❌ | ISO 8601 timestamp of first transaction |
| `last_transaction_at` | string | ❌ | ISO 8601 timestamp of most recent transaction |

### 1.3 Extensions

Extensions are **optional**. If present, they contain:

```json
{
  "extensions": {
    "partner_attestations": [ ... ],
    "counterparty_metadata": [ ... ],
    "merkle_root": "sha256_hash_of_all_counterparty_hashes"
  }
}
```

**CRITICAL CONSTRAINT**: Optional fields are **OMITTED ENTIRELY** (not `null`). A field with no value must not appear in the JSON.

### 1.4 Partner Attestations

Partner attestations attach verified claims to a VAC credential:

```json
{
  "partner_attestations": [
    {
      "partner_id": "uuid-of-partner",
      "partner_name": "Corpo Legal Services",
      "partner_type": "corpo",
      "claims": {
        "legal_entity_id": "CORP-12345-DE",
        "jurisdiction": "Germany",
        "compliance_status": "verified"
      },
      "issued_at": "2026-03-20T10:00:00Z"
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `partner_id` | string | ✅ | UUID of the attesting partner |
| `partner_name` | string | ✅ | Human-readable partner name |
| `partner_type` | string | ✅ | Type: 'corpo', 'verifier', 'counterparty', 'infrastructure' |
| `claims` | object | ✅ | Arbitrary JSON object with attested claims |
| `issued_at` | string | ✅ | ISO 8601 timestamp of attestation |
| `expires_at` | string | ❌ | Optional expiration timestamp |

#### Corpo `legal_entity_id` Migration

Per VAC v0.3, the `legal_entity_id` field is **migrated** from the agent table to `extensions.partner_attestations.corpo.claims.legal_entity_id`.

**This is a HARD CUTOVER** — no backward compatibility. Agents must use the new location.

### 1.5 Counterparty Metadata

Counterparty metadata uses hash anchoring for privacy:

```json
{
  "counterparty_metadata": [
    {
      "counterparty_id": "hashed_counterparty_id",
      "metadata_hash": "sha256_hash_of_encrypted_metadata",
      "merkle_root": "merkle_root_for_batch_verification",
      "ipfs_cid": "QmXyz123..."
    }
  ],
  "merkle_root": "overall_merkle_root"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `counterparty_id` | string | ✅ | Hashed identifier of counterparty |
| `metadata_hash` | string | ✅ | SHA256 hash of encrypted metadata |
| `merkle_root` | string | ❌ | Merkle root for batch verification |
| `ipfs_cid` | string | ❌ | IPFS Content ID for off-chain storage |

The actual metadata is **not stored on-chain**. Only the hash is anchored to the VAC. The full metadata can be retrieved via IPFS (if CID provided) or through partner APIs.

---

## 2. Cryptographic Signing

### 2.1 Canonical JSON

Before signing, the VAC is converted to **canonical JSON**:
- Keys sorted alphabetically
- No whitespace (compact format)
- No `null` values (omit optional fields entirely)

Example:
```json
{"core":{"agent_id":"abc123","rails_used":["lightning"],...},"credential_id":"vac_...",...}
```

### 2.2 Signature Algorithm

VACs are signed using the OP's private key. Supported algorithms:
- **Ed25519**: For Solana-compatible agents
- **SECP256k1**: For Ethereum/Bitcoin-compatible agents

The signature covers the canonical JSON string of the entire VAC (excluding the `signature` field itself).

### 2.3 Verification

To verify a VAC:
1. Remove the `signature` field
2. Generate canonical JSON
3. Verify signature using OP's public key
4. Check that `expires_at` has not passed
5. Verify no fields are `null` (all optional fields must be omitted)

---

## 3. Credential Lifecycle

### 3.1 Issuance

VACs are issued automatically when:
- An agent queries `/vac/{agent_id}` and no valid VAC exists
- A background refresh job runs (every 24 hours)

### 3.2 Refresh

VACs automatically refresh every **24 hours**. The new VAC:
- Has a fresh 7-day expiration
- Contains updated core fields from recent transactions
- Preserves active attestations

### 3.3 Expiration

VACs expire after **7 days maximum**. Expired VACs:
- Are rejected by verification
- Cannot be renewed (must be reissued)
- Remain in the credential history

### 3.4 Revocation

VACs can be revoked for reasons:
- `compromise`: Private key or credential compromised
- `expiry`: Natural expiration (rarely manually triggered)
- `violation`: Terms of service violation
- `request`: Agent-requested revocation
- `other`: Other reasons

Revoked VACs are permanently invalidated. A new credential must be issued.

### 3.5 Revocation Registry

All revocations are logged immutably in the revocation registry:

```
GET /vac/revocations
```

Returns:
```json
{
  "revocations": [
    {
      "revocation_id": "uuid",
      "credential_id": "vac_...",
      "agent_id": "agent_id",
      "revoked_at": "2026-03-23T16:00:00Z",
      "reason": "compromise",
      "webhook_delivered": true
    }
  ]
}
```

---

## 4. API Reference

### 4.1 Base URL
```
https://api.agenticterminal.ai
```

### 4.2 VAC Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/vac/{agent_id}` | None | Get active VAC for agent |
| POST | `/vac/{agent_id}/refresh` | API Key | Force VAC refresh |
| GET | `/vac/{agent_id}/history` | None | Get VAC history |
| GET | `/vac/{agent_id}/attestations` | None | Get partner attestations |
| GET | `/vac/{agent_id}/legal-entity` | None | Get legal entity attestation |

### 4.3 Partner Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/vac/partners/register` | API Key | Register new partner |
| GET | `/vac/partners` | None | List partners |
| GET | `/vac/partners/{id}` | None | Get partner details |
| POST | `/vac/partners/{id}/attest` | Partner Auth | Issue attestation |

### 4.4 Counterparty Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/vac/{cred_id}/counterparty` | API Key | Add counterparty metadata |
| GET | `/vac/{cred_id}/counterparty` | None | Get counterparty hashes |

### 4.5 Revocation Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/vac/revocations` | None | List revocations |
| POST | `/vac/{cred_id}/revoke` | API Key | Revoke credential |

### 4.6 Corpo Migration Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/vac/corpo/register` | API Key | Register Corpo partner |
| POST | `/vac/corpo/{id}/attest-entity` | Partner Auth | Attest legal entity |

---

## 5. Schema Definition

### 5.1 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Verified Agent Credential",
  "type": "object",
  "required": ["version", "issued_at", "expires_at", "credential_id", "core", "signature"],
  "properties": {
    "version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$"
    },
    "issued_at": {
      "type": "string",
      "format": "date-time"
    },
    "expires_at": {
      "type": "string",
      "format": "date-time"
    },
    "credential_id": {
      "type": "string",
      "pattern": "^vac_[a-zA-Z0-9_]+$"
    },
    "core": {
      "type": "object",
      "required": ["agent_id", "total_transactions", "total_volume_sats", "unique_counterparty_count", "rails_used"],
      "properties": {
        "agent_id": { "type": "string" },
        "total_transactions": { "type": "integer", "minimum": 0 },
        "total_volume_sats": { "type": "integer", "minimum": 0 },
        "unique_counterparty_count": { "type": "integer", "minimum": 0 },
        "rails_used": {
          "type": "array",
          "items": { "type": "string" }
        },
        "first_transaction_at": { "type": "string", "format": "date-time" },
        "last_transaction_at": { "type": "string", "format": "date-time" }
      },
      "additionalProperties": false
    },
    "extensions": {
      "type": "object",
      "properties": {
        "partner_attestations": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["partner_id", "partner_name", "partner_type", "claims", "issued_at"],
            "properties": {
              "partner_id": { "type": "string", "format": "uuid" },
              "partner_name": { "type": "string" },
              "partner_type": {
                "type": "string",
                "enum": ["corpo", "verifier", "counterparty", "infrastructure"]
              },
              "claims": { "type": "object" },
              "issued_at": { "type": "string", "format": "date-time" },
              "expires_at": { "type": "string", "format": "date-time" }
            }
          }
        },
        "counterparty_metadata": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["counterparty_id", "metadata_hash"],
            "properties": {
              "counterparty_id": { "type": "string" },
              "metadata_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
              "merkle_root": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
              "ipfs_cid": { "type": "string" }
            }
          }
        },
        "merkle_root": { "type": "string", "pattern": "^[a-f0-9]{64}$" }
      }
    },
    "signature": {
      "type": "string",
      "pattern": "^[a-f0-9]+$"
    }
  }
}
```

---

## 6. Migration from ARP

### 6.1 ARP to VAC Mapping

| ARP Field | VAC Location | Notes |
|-----------|--------------|-------|
| `event_id` | N/A | VAC is credential, not event |
| `arp_version` | `version` | Renamed |
| `agent_id` | `core.agent_id` | Same |
| `protocol` | `core.rails_used[]` | Expanded to array |
| `amount_bucket` | N/A | Computed on demand |
| `legal_entity_id` | `extensions.partner_attestations.corpo.claims.legal_entity_id` | **Migrated** |

### 6.2 legal_entity_id Migration

**OLD (ARP):**
```json
{
  "agent_id": "abc123",
  "legal_entity_id": "CORP-12345-DE"
}
```

**NEW (VAC v0.3):**
```json
{
  "core": { "agent_id": "abc123" },
  "extensions": {
    "partner_attestations": [{
      "partner_type": "corpo",
      "claims": {
        "legal_entity_id": "CORP-12345-DE"
      }
    }]
  }
}
```

### 6.3 Migration Timeline

1. **Phase 1**: Implement VAC endpoints alongside ARP
2. **Phase 2**: Register Corpo partners and migrate existing legal_entity_id values
3. **Phase 3**: Deprecate ARP endpoints
4. **Phase 4**: Remove legacy legal_entity_id field from agent table

---

## 7. Security Considerations

### 7.1 Privacy

- Only hashes are stored on-chain
- Full metadata is off-chain (IPFS or partner APIs)
- Counterparty IDs are hashed
- Amount buckets preserve privacy vs. exact values

### 7.2 Verification

- All VACs are signed by OP
- Partner attestations are signed by partners
- Revocation is immutable and auditable

### 7.3 Revocation

- Immediate effect upon revocation
- Webhook notifications to partners
- Revocation registry is append-only

---

## 8. Attestation Scoping & Hybrid Trust Model (v0.3)

### 8.1 Trust Levels

VAC v0.3 introduces a **5-level trust hierarchy** for attestations:

| Level | Name | Description | Use Case |
|-------|------|-------------|----------|
| **LEVEL_0** | No Attestation / Revoked | No valid attestation exists or attestation has been revoked | Initial state or after revocation |
| **LEVEL_1** | Self-Attested | Claims made by the agent itself without external verification | Bootstrapping, personal claims |
| **LEVEL_2** | Counterparty Attested | Claims attested by transaction counterparties with cryptographic signatures | Transaction-based reputation |
| **LEVEL_3** | Partner Attested | Claims attested by registered protocol partners (KYB verified) | Business verification |
| **LEVEL_4** | Organization Attested | Claims attested by registered organizations with legal entity backing | Enterprise verification |
| **LEVEL_5** | OP Verified | Claims directly verified by Observer Protocol with protocol-level cryptographic proof | Maximum trust |

### 8.2 Attestation Scopes

Attestations can cover different aspects of an agent:

| Scope | Description | Typical Attester |
|-------|-------------|------------------|
| **IDENTITY** | Identity verification (who is this agent) | OP, Verifier partners |
| **LEGAL_ENTITY** | Legal entity wrapper and compliance | Corpo partners |
| **COMPLIANCE** | Regulatory compliance status | Verifier partners |
| **REPUTATION** | Reputation score and history | OP, Counterparties |
| **CAPABILITY** | Technical capabilities and features | Infrastructure partners |
| **TRANSACTION** | Transaction history verification | OP, Counterparties |
| **INFRASTRUCTURE** | Infrastructure provider verification | Infrastructure partners |
| **CUSTOM** | Custom attestation scopes | Any partner type |

### 8.3 Hybrid Trust Model

The hybrid model combines on-chain and off-chain verification:

**On-Chain (Cryptographic):**
- Ed25519/SECP256k1 signatures
- SHA256 hash commitments
- Merkle root anchoring
- Immutable revocation registry

**Off-Chain (Operational):**
- Partner KYB verification
- Legal entity checks
- Reputation score computation
- Webhook notifications

### 8.4 Attestation Structure

```json
{
  "attestation": {
    "agent_id": "agent_123",
    "trust_level": 3,
    "scope": "legal_entity",
    "claims": {
      "legal_entity_id": "CORP-456",
      "jurisdiction": "Delaware"
    },
    "attester": {
      "type": "partner",
      "id": "partner_789",
      "name": "LegalVerify Inc."
    },
    "proof": {
      "signature": "hex_signature",
      "signer_public_key": "hex_pubkey",
      "timestamp": "2026-03-27T14:00:00Z",
      "hash_algorithm": "sha256"
    },
    "on_chain_anchor": {
      "tx_hash": "0xabc...",
      "block_number": 12345678,
      "merkle_root": "sha256_hash"
    }
  }
}
```

### 8.5 Validation Rules

Attestations are validated according to their trust level:

**LEVEL_1 (Self-Attested):**
- Must include agent signature
- No external verification required
- Lower weight in trust calculations

**LEVEL_2-4 (Partner/Org Attested):**
- Must include attester signature
- Attester must be registered and verified
- Attestation must not be expired
- Attester must have appropriate scope permissions

**LEVEL_5 (OP Verified):**
- Must include OP protocol signature
- Full cryptographic verification required
- Highest weight in trust calculations

---

## 8.6 Counterparty Quality Claims (v0.3.2)

Quality claims provide structured attestations from counterparties about transaction quality, enabling AT-ARS (Agent Terminal - Agent Reputation System) reputation scoring. These attestations capture completion status, accuracy ratings, dispute flags, and optional hashed notes.

### 8.6.1 Quality Claims Schema

```json
{
  "quality_claims": {
    "completion_status": "complete",
    "accuracy_rating": 5,
    "dispute_raised": false,
    "payment_settled": true,
    "quality_schema_version": "0.3.2",
    "completion_percentage": 100,
    "notes_hash": "a1b2c3d4e5f6...",
    "notes_retrieval_url": "https://api.agenticterminal.ai/ars/notes/txn_123"
  }
}
```

### 8.6.2 Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `completion_status` | string | ✅ | Job completion state: `"complete"`, `"partial"`, `"failed"`, `"cancelled"` |
| `accuracy_rating` | integer | ✅ | Quality score 1-5 (1=poor, 5=excellent) |
| `dispute_raised` | boolean | ✅ | Whether a dispute was raised for this transaction |
| `payment_settled` | boolean | ✅ | Whether payment was successfully settled |
| `quality_schema_version` | string | ✅ | Schema version (e.g., `"0.3.2"`) |
| `completion_percentage` | integer | ❌ | Required when `completion_status="partial"`. Integer 0-100 |
| `notes_hash` | string | ❌ | SHA256 hash of freetext notes (64-char hex) |
| `notes_retrieval_url` | string | ❌ | AT ARS endpoint URL for notes retrieval |

### 8.6.3 Validation Rules

**Required Fields:**
All quality claims MUST include `completion_status`, `accuracy_rating`, `dispute_raised`, `payment_settled`, and `quality_schema_version`.

**Enum Validation:**
- `completion_status` MUST be one of: `"complete"`, `"partial"`, `"failed"`, `"cancelled"`

**Range Validation:**
- `accuracy_rating` MUST be an integer 1-5
- `completion_percentage` MUST be an integer 0-100 (required when `completion_status="partial"`)

**Boolean Validation:**
- `dispute_raised` MUST be a boolean
- `payment_settled` MUST be a boolean

**Hash Validation (Optional):**
- `notes_hash` MUST be a 64-character hexadecimal string (valid SHA256)

### 8.6.4 Attestation Structure

Quality claims are submitted as counterpartner attestations:

```json
{
  "attestation": {
    "partner_id": "uuid-of-counterparty",
    "partner_type": "counterparty",
    "agent_id": "agent-being-rated",
    "claims": {
      "transaction_id": "txn_abc123",
      "attestation_type": "quality_claim",
      "quality_claims": {
        "completion_status": "partial",
        "accuracy_rating": 3,
        "dispute_raised": false,
        "payment_settled": true,
        "quality_schema_version": "0.3.2",
        "completion_percentage": 75,
        "notes_hash": "a1b2c3d4e5f6...",
        "notes_retrieval_url": "https://api.agenticterminal.ai/ars/notes/txn_abc123"
      }
    },
    "issued_at": "2026-03-27T14:00:00Z",
    "attestation_signature": "hex_signature"
  }
}
```

### 8.6.5 Notes Retrieval Mechanics

Counterparties may submit freetext notes at any time via the AT ARS endpoint. The notes are hashed and verified against the stored `notes_hash`.

**Storage Flow:**
1. Counterparty computes `notes_hash = SHA256(notes_text)`
2. Counterparty submits quality claim with `notes_hash` and optional `notes_retrieval_url`
3. AT stores hash with `retrieval_status: "pending"`

**Retrieval Flow:**
1. Counterparty submits notes text to `POST /ars/notes/{transaction_id}`
2. AT computes hash of submitted text
3. AT verifies hash matches stored `notes_hash`
4. If match: AT updates `retrieval_status` to `"retrieved"` and stores notes
5. If mismatch: Return error, status remains `"pending"`

### 8.6.6 API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/vac/partners/{id}/attest` | Partner Auth | Submit quality claim attestation |
| POST | `/ars/notes/{transaction_id}` | API Key | Submit notes text for hash verification |
| GET | `/ars/notes/{transaction_id}/status` | API Key | Check notes retrieval status |

### 8.6.7 VAC Extension Format

Quality claims appear in VAC credentials under `extensions.quality_claims`:

```json
{
  "extensions": {
    "quality_claims": [
      {
        "transaction_id": "txn_abc123",
        "completion_status": "partial",
        "accuracy_rating": 3,
        "dispute_raised": false,
        "payment_settled": true,
        "quality_schema_version": "0.3.2",
        "completion_percentage": 75,
        "notes_hash": "a1b2c3d4e5f6...",
        "notes_retrieval_url": "https://api.agenticterminal.ai/ars/notes/txn_abc123",
        "submitted_at": "2026-03-27T14:00:00Z",
        "partner_id": "uuid-of-counterparty",
        "partner_name": "Service Provider Inc."
      }
    ]
  }
}
```

### 8.6.8 Reputation Scoring

AT-ARS uses quality claims for reputation calculations:

**Signal Weights:**
- `completion_status=complete` → +1.0 reputation
- `completion_status=partial` → +0.5 reputation (scaled by completion_percentage)
- `completion_status=failed` → -0.5 reputation
- `completion_status=cancelled` → 0.0 reputation
- `accuracy_rating` → Weighted 0.2-1.0 (1=0.2, 5=1.0)
- `dispute_raised=true` → -1.0 reputation (independent of completion)
- `payment_settled=true` → +0.5 reputation
- `payment_settled=false` → -0.5 reputation

**Aggregation:**
Reputation scores are computed as weighted averages across all quality claims, with more recent claims having higher weight (exponential decay).

---

## 9. Webhook Delivery on Revocation

### 9.1 Webhook Configuration

Partners can configure webhooks to receive revocation notifications:

```json
{
  "webhook": {
    "url": "https://partner.example.com/webhooks/op-revocation",
    "secret": "whsec_...",
    "events": ["vac.revoked", "attestation.revoked"],
    "retry_policy": {
      "max_retries": 5,
      "backoff_seconds": [1, 2, 4, 8, 16]
    }
  }
}
```

### 9.2 Webhook Payload

```json
{
  "event": "vac.revoked",
  "timestamp": "2026-03-27T14:00:00Z",
  "data": {
    "revocation_id": "rev_abc123",
    "credential_id": "vac_agent123_...",
    "agent_id": "agent_123",
    "revoked_at": "2026-03-27T14:00:00Z",
    "reason": "compromise",
    "reason_details": "Private key compromised in security incident",
    "previous_attestations": ["att_1", "att_2"]
  },
  "signature": "hmac_sha256_signature"
}
```

### 9.3 Signature Verification

Webhooks are signed with HMAC-SHA256:

```
Signature = HMAC-SHA256(secret, timestamp + "." + payload)
```

Partners must verify the signature to ensure authenticity.

### 9.4 Delivery Guarantees

- **At-least-once delivery**: Webhooks may be delivered multiple times
- **Idempotency**: Use `revocation_id` to deduplicate
- **Retry logic**: Exponential backoff up to 5 retries
- **Timeout**: 30 second timeout per delivery attempt

---

## 10. Environment Configuration

### 10.1 CORS Configuration

CORS is configurable via environment variables:

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `OP_CORS_MODE` | `open`, `production` | `production` | CORS mode |
| `OP_ALLOWED_ORIGINS` | Comma-separated URLs | `*` (if open) | Allowed origins |

**Development Mode:**
```bash
OP_CORS_MODE=open
# Allows all origins
```

**Production Mode:**
```bash
OP_CORS_MODE=production
OP_ALLOWED_ORIGINS=https://observerprotocol.org,https://www.observerprotocol.org
```

### 10.2 File Paths

All file paths are configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OP_WORKSPACE_PATH` | `.` | Base workspace directory |
| `OP_REPO_PATH` | `.` | Repository root path |
| `OP_DATA_PATH` | `./data` | Data storage directory |

No hardcoded `/home/futurebit/` paths remain in the codebase.

---

## 11. Known Limitations (v0.3)

- IPFS integration requires external pinning service
- Merkle root calculation is simplified (not full binary tree)
- Batch counterparty metadata submission not yet implemented
- Webhook delivery is best-effort, not guaranteed

---

## Appendix A: Example VAC Credential

```json
{
  "version": "1.0.0",
  "issued_at": "2026-03-23T16:00:00Z",
  "expires_at": "2026-03-30T16:00:00Z",
  "credential_id": "vac_abc123def456_7a8b9c0d",
  "core": {
    "agent_id": "abc123def456",
    "total_transactions": 42,
    "total_volume_sats": 1500000,
    "unique_counterparty_count": 7,
    "rails_used": ["lightning", "L402"],
    "first_transaction_at": "2026-02-01T10:00:00Z",
    "last_transaction_at": "2026-03-22T14:30:00Z"
  },
  "extensions": {
    "partner_attestations": [
      {
        "partner_id": "550e8400-e29b-41d4-a716-446655440000",
        "partner_name": "Corpo Legal Services",
        "partner_type": "corpo",
        "claims": {
          "legal_entity_id": "CORP-12345-DE",
          "jurisdiction": "Germany"
        },
        "issued_at": "2026-03-20T10:00:00Z"
      }
    ],
    "counterparty_metadata": [
      {
        "counterparty_id": "sha256:def789...",
        "metadata_hash": "a1b2c3d4e5f6...",
        "merkle_root": "m1n2o3p4q5r6..."
      }
    ]
  },
  "signature": "3045022100abc123..."
}
```

---

## 12. Changelog

### v0.3.2 (2026-03-27)

**New Features:**
- **Counterparty Quality Claims (§8.6)**: Structured quality attestations from counterparties
  - Completion status tracking (complete, partial, failed, cancelled)
  - Accuracy ratings (1-5 scale)
  - Dispute and payment settlement flags
  - Optional hashed notes with retrieval mechanics
- **AT-ARS Integration**: Quality claims feed into Agent Terminal reputation scoring
- **Notes Hash Verification**: Cryptographic verification of freetext notes via `POST /ars/notes/{transaction_id}`
- **Quality Claims Schema**: Full validation for `completion_status`, `accuracy_rating`, `dispute_raised`, `payment_settled`, `completion_percentage`
- **Notes Retrieval API**: New endpoints for submitting and verifying notes against stored hashes

**New API Endpoints:**
- `POST /ars/notes/{transaction_id}` — Submit freetext notes for hash verification
- `GET /ars/notes/{transaction_id}/status` — Check notes retrieval status

**Data Model Changes:**
- Added `quality_claims_notes` table for notes hash storage and retrieval tracking
- Added `quality_claims` field to VAC extensions
- Added `attestation_type` discriminator for counterparty attestations

**Validation:**
- Server-side validation of all quality claim fields
- Conditional `completion_percentage` required when status is "partial"
- SHA256 hash format validation for notes_hash
- Boolean type enforcement for dispute_raised and payment_settled

---

### v0.3.1 (2026-03-27)

**New Features:**
- **Attestation Scoping**: 5-level trust hierarchy (LEVEL_0 to LEVEL_5)
- **Hybrid Trust Model**: Combined on-chain/off-chain verification
- **Attestation Scopes**: 8 scope types (identity, legal_entity, compliance, etc.)
- **Webhook Delivery**: Async webhook notifications on VAC revocation
- **CORS Configuration**: Environment-based CORS (open/production modes)
- **E2E Protocol Tests**: Full end-to-end test suite

**Improvements:**
- **UUID4 for event_id**: All events use cryptographically secure UUID4
- **Bucket Midpoints**: Fixed total_volume_sats calculation with proper bucket midpoints
- **Code Quality**: Removed dead code (verify_ecdsa_signature)
- **Path Configuration**: All paths use environment variables (no hardcoded paths)

**Bug Fixes:**
- Fixed hardcoded `/home/futurebit/` paths across 10 files
- Fixed CORS to be configurable via `OP_CORS_MODE` and `OP_ALLOWED_ORIGINS`
- Fixed total_volume_sats aggregation using bucket midpoints
- Fixed agent lookup endpoint (singular vs plural)

**Security:**
- All attestations include cryptographic proofs
- Webhook signatures use HMAC-SHA256
- Trust level validation enforced
- Revocation registry is append-only

### v0.3 (2026-03-23)

**Initial VAC Specification:**
- Core VAC structure (core + extensions)
- Partner attestations framework
- Counterparty metadata with hash anchoring
- Credential lifecycle (issuance, refresh, expiration, revocation)
- JSON Schema definition
- API reference
- Migration guide from ARP

---

*VAC v0.3.1 — March 2026*  
*License: CC BY 4.0*  
*Contribute: [github.com/observer-protocol/vac-spec](https://github.com/observer-protocol/vac-spec)*
