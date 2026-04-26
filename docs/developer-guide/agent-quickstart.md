# Agent Developer Quickstart

Register your agent on Observer Protocol, prove key ownership, and retrieve your Verified Agent Credential — in 15 minutes.

## Prerequisites

- An Ed25519 keypair (your agent's identity)
- `curl` or any HTTP client

If you're running a Lightning node with Alby, your node's public key is your Ed25519 key.

## Step 1: Register your agent

```bash
curl -X POST https://api.observerprotocol.org/observer/register-agent \
  -H "Content-Type: application/json" \
  -d '{
    "public_key": "YOUR_ED25519_PUBLIC_KEY_HEX",
    "agent_name": "My Agent"
  }'
```

**Response:**
```json
{
  "agent_id": "d13cdfce...",
  "agent_did": "did:web:observerprotocol.org:agents:d13cdfce...",
  "verification_status": "registered",
  "did_document": { ... },
  "next_steps": [
    "Complete challenge-response verification to prove key ownership"
  ]
}
```

Your agent now has a DID. Save the `agent_id` — you'll need it for everything else.

## Step 2: Prove key ownership

OP needs to verify you control the private key corresponding to the public key you registered.

### 2a. Request a challenge

```bash
curl -X POST "https://api.observerprotocol.org/observer/challenge?agent_id=YOUR_AGENT_ID"
```

**Response:**
```json
{
  "challenge_id": "ch_abc123",
  "nonce": "a1b2c3d4e5f6...",
  "expires_at": "2026-04-25T15:05:00Z",
  "expires_in_seconds": 300
}
```

### 2b. Sign the nonce

Sign the `nonce` string with your Ed25519 private key. The signature must be hex-encoded.

**Python:**
```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex("YOUR_PRIVATE_KEY_HEX"))
signature = private_key.sign(b"a1b2c3d4e5f6...")  # the nonce bytes
signature_hex = signature.hex()
```

**JavaScript (Node.js):**
```javascript
import { sign } from 'crypto';
import { createPrivateKey } from 'crypto';

const key = createPrivateKey({
  key: Buffer.from('YOUR_PRIVATE_KEY_HEX', 'hex'),
  format: 'der',
  type: 'pkcs8'
});
const signature = sign(null, Buffer.from('a1b2c3d4e5f6...'), key);
const signatureHex = signature.toString('hex');
```

### 2c. Submit the signed challenge

```bash
curl -X POST "https://api.observerprotocol.org/observer/verify-agent?agent_id=YOUR_AGENT_ID&signed_challenge=YOUR_SIGNATURE_HEX"
```

**Response:**
```json
{
  "verified": true,
  "agent_id": "d13cdfce...",
  "verification_method": "challenge_response_ed25519",
  "message": "Agent verified successfully"
}
```

Your agent is now verified on Observer Protocol.

## Step 3: View your DID document

Your agent's DID document is publicly resolvable:

```bash
curl https://api.observerprotocol.org/agents/YOUR_AGENT_ID/did.json
```

**Response:**
```json
{
  "@context": ["https://www.w3.org/ns/did/v1", "https://w3id.org/security/suites/ed25519-2020/v1"],
  "id": "did:web:observerprotocol.org:agents:d13cdfce...",
  "verificationMethod": [{
    "id": "did:web:observerprotocol.org:agents:d13cdfce...#key-1",
    "type": "Ed25519VerificationKey2020",
    "controller": "did:web:observerprotocol.org:agents:d13cdfce...",
    "publicKeyMultibase": "z..."
  }],
  "assertionMethod": ["did:web:observerprotocol.org:agents:d13cdfce...#key-1"]
}
```

Anyone can resolve this document and verify your agent's credentials without contacting OP.

## Step 4: Retrieve your VAC

The Verified Agent Credential is your agent's portable identity:

```bash
curl https://api.observerprotocol.org/vac/YOUR_AGENT_ID
```

The VAC is a signed W3C Verifiable Presentation containing your agent's credentials, attestations, and extension references.

## Step 5: Check your trust score

```bash
curl https://api.observerprotocol.org/api/v1/trust/score/YOUR_AGENT_ID
```

**Response:**
```json
{
  "agent_id": "d13cdfce...",
  "trust_score": 42,
  "source_rail": "aggregate"
}
```

The trust score starts low and increases as your agent builds verified transaction history. See [AT-ARS Trust Score](./trust-score.md) for the methodology.

## Step 6: View your agent on Sovereign

Your agent has a public profile:

```
https://app.agenticterminal.io/sovereign/agents/YOUR_AGENT_ID
```

Share this URL with anyone. It shows your agent's verified attestations, trust score, and cryptographic details — no login required.

## What's next

- **Submit verified activity** — When your agent transacts on Lightning or TRON, submit activity credentials via `POST /audit/activity`. See [API Reference](./api-reference.md).
- **Get attestations** — Partner with KYB providers, compliance attestors, or other OP partners to get attestation credentials. See [API Reference](./api-reference.md).
- **Build trust** — Your AT-ARS score increases with verified transactions, counterparty diversity, and attestations. See [Trust Score](./trust-score.md).

## Using the JavaScript SDK

```javascript
import ObserverClient from '@observerprotocol/sdk';

const client = new ObserverClient({
  baseUrl: 'https://api.observerprotocol.org',
  agentId: 'YOUR_AGENT_ID',
  privateKey: 'YOUR_PRIVATE_KEY_HEX'
});

// Register
await client.register({ alias: 'My Agent' });

// Record a transaction
await client.recordTransaction({
  txSignature: 'abc123...',
  senderAddress: '...',
  recipientAddress: '...',
  amount: 1000,
  protocol: 'lightning'
});
```

The SDK wraps the REST API. All SDK operations are also available as direct HTTP calls documented in the [API Reference](./api-reference.md).
