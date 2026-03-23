# VAC Specification v0.3
## Verified Agent Credential

**Status:** Draft  
**Version:** 0.3  
**Date:** 2026-03-23  
**License:** CC BY 4.0  
**Authors:** Observer Protocol contributors  

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

## 8. Known Limitations (v0.3)

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

*VAC v0.3 — March 2026*  
*License: CC BY 4.0*  
*Contribute: [github.com/observer-protocol/vac-spec](https://github.com/observer-protocol/vac-spec)*
