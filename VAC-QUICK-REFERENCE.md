# VAC Quick Reference

## Getting a VAC Credential

```bash
# Get VAC for an agent
curl https://api.agenticterminal.ai/vac/{agent_id}

# Response:
{
  "version": "1.0.0",
  "issued_at": "2026-03-23T16:00:00Z",
  "expires_at": "2026-03-30T16:00:00Z",
  "credential_id": "vac_agent123_abc456",
  "core": {
    "agent_id": "agent123",
    "total_transactions": 42,
    "total_volume_sats": 1500000,
    "unique_counterparty_count": 7,
    "rails_used": ["lightning", "L402"]
  },
  "extensions": {
    "partner_attestations": [
      {
        "partner_id": "...",
        "partner_name": "Corpo Legal",
        "partner_type": "corpo",
        "claims": {
          "legal_entity_id": "CORP-12345-DE"
        },
        "issued_at": "2026-03-20T10:00:00Z"
      }
    ]
  },
  "signature": "..."
}
```

## Registering a Partner

```bash
# Register a Corpo partner
curl -X POST https://api.agenticterminal.ai/vac/corpo/register \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "legal_entity_name": "Corpo Legal Services",
    "public_key": "ed25519_pubkey_hex",
    "webhook_url": "https://corpo.example.com/webhooks/vac"
  }'
```

## Issuing an Attestation

```bash
# Issue legal entity attestation
curl -X POST https://api.agenticterminal.ai/vac/corpo/{partner_id}/attest-entity \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PARTNER_KEY" \
  -d '{
    "agent_id": "agent123",
    "legal_entity_id": "CORP-12345-DE",
    "jurisdiction": "Germany",
    "attestation_signature": "signed_claims_hex"
  }'
```

## Getting Legal Entity Attestation (VAC v0.3 Format)

```bash
# Get legal_entity_id from partner attestations
curl https://api.agenticterminal.ai/vac/{agent_id}/legal-entity

# Response:
{
  "agent_id": "agent123",
  "legal_entity_id": "CORP-12345-DE",
  "jurisdiction": "Germany",
  "attested_by": "Corpo Legal Services",
  "attested_at": "2026-03-20T10:00:00Z",
  "source": "vac_partner_attestation",
  "format": "VAC v0.3"
}
```

## Revoking a Credential

```bash
# Revoke a VAC credential
curl -X POST https://api.agenticterminal.ai/vac/{credential_id}/revoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "reason": "compromise",
    "details": "Private key compromised"
  }'
```

## Checking Revocation Registry

```bash
# List all revocations
curl https://api.agenticterminal.ai/vac/revocations

# List revocations for specific agent
curl "https://api.agenticterminal.ai/vac/revocations?agent_id=agent123"
```

## Background Refresh

VACs automatically refresh every 24 hours. To force a refresh:

```bash
curl -X POST https://api.agenticterminal.ai/vac/{agent_id}/refresh \
  -H "Authorization: Bearer $API_KEY"
```

## Verification

To verify a VAC signature:

```python
from crypto_verification import verify_vac_signature

is_valid = verify_vac_signature(vac_payload, signature_hex, op_public_key)
```

## VAC Semantics: Derived vs Raw Data

### Critical Clarification

**Agents present VAC credentials, NOT raw transaction history.**

The VAC (Verified Agent Credential) is a **derived credential** that aggregates and attests to an agent's transaction history, but it is NOT the raw transaction data itself.

| Aspect | VAC (Derived) | Raw Transaction History |
|--------|---------------|------------------------|
| **What is shared** | Aggregated metrics, attestations | Individual transaction records |
| **Privacy level** | High - only aggregated data | Low - full transaction details |
| **Verification** | Cryptographically signed by OP | Stored in database |
| **Expiration** | 7 days max | Permanent |
| **Use case** | Identity verification, reputation | Audit, compliance, debugging |

### VAC Contains (Aggregated):
- Total transaction count
- Total volume (in satoshis)
- Unique counterparty count
- Rails used (protocols)
- Partner attestations
- Counterparty metadata hashes

### VAC Does NOT Contain:
- Individual transaction hashes
- Specific timestamps of transactions
- Counterparty identities
- Transaction amounts per transaction
- Service descriptions
- Preimages or sensitive payment data

### Access Control
- **VAC endpoints** (`/vac/{agent_id}`) return derived credentials
- **Raw transaction access** requires additional authorization and is NOT available via public VAC endpoints
- Agents control what is shared via their VAC credentials
- Partners can verify VAC signatures without accessing raw data

## Important Notes

1. **VACs expire after 7 days** - Query `/vac/{agent_id}` to get fresh credentials
2. **Optional fields are omitted** - Not `null`, but entirely absent
3. **legal_entity_id moved** - Now in `extensions.partner_attestations.corpo.claims`
4. **All VACs are signed** - Verify using OP's public key
5. **VACs are derived credentials** - They represent aggregated history, not raw transaction data
