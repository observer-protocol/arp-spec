# VAC Extensions

Third-party platforms can attach their own attestation data to an agent's VAC. Your reputation scores, compliance data, or rating systems become portable, verifiable credentials that travel with the agent.

## How it works

1. You **register** an extension schema (one-time setup)
2. You **issue** attestation credentials for agents on your platform
3. The attestation appears in the agent's **VAC** and **Sovereign profile**
4. Any verifier can **check** your attestation by verifying your Ed25519 signature against your DID

## Trust model

OP attests that your extension schema is registered and your DID is resolvable. **OP does NOT attest that your data is truthful.** Trust in extension data is the verifier's decision, based on their trust in you as an issuer.

This is the same trust model as the broader W3C VC ecosystem. Your reputation score carries weight because parties trust your methodology — not because OP endorses it.

## Register an extension

```bash
curl -X POST https://api.observerprotocol.org/v1/vac/extensions/register \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "extension_id": "yourplatform_reputation_v1",
    "display_name": "YourPlatform Reputation Score",
    "issuer": {
      "did": "did:web:yourplatform.com:op-identity",
      "display_name": "YourPlatform",
      "domain": "yourplatform.com"
    },
    "schema": {
      "type": "object",
      "required": ["score", "last_evaluated"],
      "properties": {
        "score": { "type": "integer", "minimum": 0, "maximum": 1000 },
        "transaction_count": { "type": "integer" },
        "last_evaluated": { "type": "string", "format": "date-time" }
      }
    }
  }'
```

**Response (201):**
```json
{
  "status": "registered",
  "extension_id": "yourplatform_reputation_v1",
  "namespace": "yourplatform_reputation",
  "schema_url": "https://observerprotocol.org/schemas/extensions/yourplatform_reputation/v1",
  "registered_at": "2026-04-25T10:00:00Z"
}
```

## Namespace rules

Extensions use integrator-prefixed namespaces to prevent collision:

- **Your namespace must derive from your registered domain or integrator ID.** `yourplatform.com` → `yourplatform_*` namespace.
- **Reserved prefixes** (`op_`, `at_`, `lightning_`, `stacks_`, `tron_`, `bitcoin_`, `ethereum_`, `solana_`) cannot be claimed by integrators.
- **First registrant claims the namespace.** Subsequent versions (`yourplatform_reputation_v2`) must come from the same integrator.
- **Identity-verified.** Your issuer DID domain must match your integrator registration.

## Issue an attestation

Extension attestations are **pre-signed** W3C Verifiable Credentials. You sign the credential with your own key (issuer-direct signing — OP never touches your key).

```bash
curl -X POST https://api.observerprotocol.org/v1/vac/extensions/attest \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "extension_id": "yourplatform_reputation_v1",
    "credential": {
      "@context": ["https://www.w3.org/ns/credentials/v2"],
      "type": ["VerifiableCredential", "YourPlatformReputationExtension"],
      "id": "urn:uuid:unique-credential-id",
      "issuer": "did:web:yourplatform.com:op-identity",
      "validFrom": "2026-04-25T10:00:00Z",
      "validUntil": "2026-05-25T10:00:00Z",
      "credentialSubject": {
        "id": "did:web:observerprotocol.org:agents:abc123",
        "extension_id": "yourplatform_reputation_v1",
        "score": 847,
        "transaction_count": 1423,
        "last_evaluated": "2026-04-25T09:55:00Z"
      },
      "proof": {
        "type": "Ed25519Signature2020",
        "created": "2026-04-25T10:00:00Z",
        "verificationMethod": "did:web:yourplatform.com:op-identity#key-1",
        "proofPurpose": "assertionMethod",
        "proofValue": "z..."
      }
    },
    "summary_fields": ["score"]
  }'
```

OP validates:
1. You are the registered extension issuer
2. The credential claims conform to the registered JSON Schema
3. The credential has a valid `proof` field

OP does NOT re-sign the credential. Your signature is the trust anchor.

## How extensions appear in the VAC

The agent's VAC gains an `extensions` array with a summary of each extension:

```json
{
  "extensions": [
    {
      "extension_id": "yourplatform_reputation_v1",
      "issuer": "did:web:yourplatform.com:op-identity",
      "credential_id": "urn:uuid:...",
      "credential_url": "https://api.observerprotocol.org/v1/attestations/...",
      "schema_url": "https://observerprotocol.org/schemas/extensions/yourplatform_reputation/v1",
      "summary": {
        "score": 847
      }
    }
  ]
}
```

Verifiers read the summary for quick consumption. For deeper verification, they fetch the full credential from `credential_url` and verify the Ed25519 signature against your DID.

## Schema versioning

- Schemas are **immutable** once published at a given version
- Breaking changes require a new version: `yourplatform_reputation_v2`
- Non-breaking additions (new optional fields) are allowed within the same version
- Multiple versions can coexist

## Lifecycle

- **Deprecate:** Mark an extension as deprecated with a successor and sunset date
- **Revoke attestations:** Use standard Bitstring Status List v1.0 revocation (your status list, not OP's)
- **Deregister:** Remove the extension entirely (existing credentials remain verifiable)
