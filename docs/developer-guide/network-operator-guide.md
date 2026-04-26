# Network Operator Guide

For engineers at networks, marketplaces, and platforms integrating Observer Protocol into their product. This guide covers what OP provides, how to integrate, and what your users experience.

## What OP gives your platform

1. **Portable agent identity.** Your users' agents get W3C DIDs that work across every OP-integrated platform — not just yours.
2. **Verified transaction history.** Agent activity is cryptographically attested, not self-reported. Your platform's attestation carries weight because it's signed by your DID.
3. **Cross-chain trust.** An agent verified on your Lightning marketplace carries that verification to a TRON platform or a Stacks dApp. Trust is composable.
4. **Extension surface.** Your platform's reputation system, compliance scores, or rating data can be registered as a VAC extension — portable, verifiable, and attached to the agent's credential.

## Integration path

### 1. Register as an integrator

Contact us at **[dev@observerprotocol.org](mailto:dev@observerprotocol.org)** to register your platform as an OP integrator. You'll receive:

- An integrator API key (Bearer token for authenticated endpoints)
- An `integrator_id` for audit trail correlation
- Sandbox access for integration testing

### 2. Verify agent transactions

When an agent transacts on your platform, verify the transaction via the chain-agnostic endpoint:

```bash
curl -X POST https://api.observerprotocol.org/v1/chain/verify \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_reference": "urn:uuid:your-unique-tx-id",
    "chain": "lightning",
    "chain_specific": {
      "payment_hash": "abc123...",
      "preimage": "def456...",
      "presenter_role": "payee"
    }
  }'
```

**Response:**
```json
{
  "verified": true,
  "receipt_reference": "urn:uuid:your-unique-tx-id",
  "chain": "lightning",
  "transaction_reference": "abc123...",
  "explorer_url": "https://mempool.space/lightning/node/...",
  "confirmed_at": "2026-04-25T10:00:00Z",
  "chain_specific": {
    "payment_hash": "abc123...",
    "preimage_verified": true,
    "verification_tier": "preimage_only"
  },
  "idempotent_replay": false
}
```

The endpoint is idempotent on `receipt_reference`. Safe to retry.

**Supported chains:**
- `lightning` — three-tier verification (payee attestation, LND query, preimage)
- `tron` — TronGrid verification for TRC-20 transactions
- `stacks` — interface defined, implementation pending

See [Chain Verification](./chain-verification.md) for full details including Lightning's payer/payee asymmetry model.

### 3. Write to the audit trail

After verifying a transaction, record it in the OP audit trail:

```bash
curl -X POST https://api.observerprotocol.org/v1/audit/verified-event \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "receipt_reference": "urn:uuid:your-unique-tx-id",
    "agent": {
      "did": "did:web:observerprotocol.org:agents:abc123",
      "agent_id": "abc123"
    },
    "transaction": {
      "amount": { "value": "0.001", "currency": "BTC" },
      "category": "ai_inference_credits",
      "rail": "lightning"
    },
    "verification": {
      "verdict": "approved",
      "verified_at": "2026-04-25T10:00:00Z"
    }
  }'
```

The event surfaces in the agent's profile on Sovereign and in the AT Enterprise dashboard. Idempotent on `receipt_reference`.

### 4. Register a VAC extension (optional)

If your platform produces reputation scores, compliance data, or other agent-relevant metrics, register them as a VAC extension:

```bash
curl -X POST https://api.observerprotocol.org/v1/vac/extensions/register \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "extension_id": "yourplatform_reputation_v1",
    "display_name": "YourPlatform Reputation Score",
    "issuer": {
      "did": "did:web:yourplatform.com:op-identity",
      "display_name": "YourPlatform"
    },
    "schema": {
      "type": "object",
      "required": ["score"],
      "properties": {
        "score": { "type": "integer", "minimum": 0, "maximum": 1000 },
        "transaction_count": { "type": "integer" },
        "last_evaluated": { "type": "string", "format": "date-time" }
      }
    }
  }'
```

Then issue extension attestations for agents on your platform:

```bash
curl -X POST https://api.observerprotocol.org/v1/vac/extensions/attest \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "extension_id": "yourplatform_reputation_v1",
    "credential": {
      "@context": ["https://www.w3.org/ns/credentials/v2"],
      "type": ["VerifiableCredential", "YourPlatformReputationExtension"],
      "issuer": "did:web:yourplatform.com:op-identity",
      "credentialSubject": {
        "id": "did:web:observerprotocol.org:agents:abc123",
        "extension_id": "yourplatform_reputation_v1",
        "score": 847,
        "transaction_count": 1423,
        "last_evaluated": "2026-04-25T09:55:00Z"
      },
      "proof": { ... }
    },
    "summary_fields": ["score"]
  }'
```

The reputation score now appears in the agent's VAC and on their Sovereign profile, attributed to your platform.

See [VAC Extensions](./vac-extensions.md) for namespace rules, schema requirements, and the full trust model.

## What your users see

When an agent registered on your platform is verified through OP:

- Their **Sovereign profile** (`app.agenticterminal.io/sovereign/agents/{id}`) shows your platform's verified transactions alongside activity from other chains
- Their **trust score** increases with each verified transaction
- Your platform's **attestations** appear alongside other partners' attestations
- Any **VAC extension** you register shows your platform's data in the agent's portable credential

## Sandbox testing

Before integrating with production, test against the sandbox:

- Same API shape as production
- Fixture agents with pre-seeded data
- Deterministic policy outcomes
- Reseedable state

See [Sandbox Environment](./sandbox.md) for setup.

## Partner network webhook integration

For network operators wanting to automatically attest agent transactions as they occur on your platform — webhook-based integration is in development.

**Current status:** The architecture supports webhook-inbound attestation, but the receiver endpoint, HMAC auth, and registered-agent filtering API are not yet shipped.

**If you're a network operator interested in webhook integration,** contact us at [dev@observerprotocol.org](mailto:dev@observerprotocol.org). Your requirements will shape the webhook API design.

## Authentication

All integrator endpoints require a Bearer token:

```
Authorization: Bearer YOUR_API_KEY
```

API keys are bound to your `integrator_id` and scoped to your audit trail. Keys are issued manually during the bootstrap period.

Rate limiting is not enforced during the bootstrap period. Production rate limits will be documented when they ship.
