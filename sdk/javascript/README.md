# Observer Protocol JavaScript SDK

Register agents, verify transactions, and manage attestations on [Observer Protocol](https://observerprotocol.org).

## Install

```bash
npm install @observer-protocol/sdk
```

## Quick start

```javascript
import { ObserverClient } from '@observer-protocol/sdk';

const client = new ObserverClient();

// Register your agent
const agent = await client.registerAgent({
  publicKey: 'your_ed25519_public_key_hex',
  agentName: 'My Agent',
});

console.log(`Agent DID: ${agent.agentDid}`);

// Request and complete challenge-response verification
const challenge = await client.requestChallenge(agent.agentId);
// Sign challenge.nonce with your Ed25519 private key...
const signature = signWithYourKey(challenge.nonce); // your signing logic
await client.verifyAgent(agent.agentId, signature);

// Retrieve your VAC
const vac = await client.getVAC(agent.agentId);

// Check your trust score
const score = await client.getTrustScore(agent.agentId);
console.log(`Trust score: ${score.trustScore}/100`);
```

## Verify a Lightning payment

```javascript
import { createHash } from 'crypto';

const client = new ObserverClient({ apiKey: 'your_api_key' });

const preimage = 'your_preimage_hex';
const paymentHash = createHash('sha256')
  .update(Buffer.from(preimage, 'hex'))
  .digest('hex');

const result = await client.verifyLightningPayment({
  receiptReference: 'urn:uuid:unique-tx-id',
  paymentHash,
  preimage,
  presenterRole: 'payee',
});

console.log(`Verified: ${result.verified}`);
console.log(`Tier: ${result.chainSpecific.verification_tier}`);
```

## Verify a TRON transaction

```javascript
const result = await client.verifyTronTransaction({
  receiptReference: 'urn:uuid:unique-tx-id',
  tronTxHash: 'abc123...',
});

console.log(`Verified: ${result.verified}`);
console.log(`TRONScan: ${result.explorerUrl}`);
```

## Register a VAC extension

```javascript
// Register your platform's reputation system
await client.registerExtension({
  extensionId: 'myplatform_reputation_v1',
  displayName: 'My Reputation Score',
  issuerDid: 'did:web:myplatform.com:op-identity',
  schema: {
    type: 'object',
    properties: {
      score: { type: 'integer', minimum: 0, maximum: 1000 },
      lastEvaluated: { type: 'string', format: 'date-time' },
    },
  },
});

// Issue an attestation for an agent
await client.submitExtensionAttestation({
  extensionId: 'myplatform_reputation_v1',
  credential: { /* pre-signed W3C VC */ },
  summaryFields: ['score'],
});
```

## Get agent data

```javascript
// Profile
const agent = await client.getAgent('agent_id');
console.log(`${agent.agentName}: ${agent.trustScore}/100`);

// Attestations
const attestations = await client.getAttestations('agent_id');
attestations.forEach(att => console.log(`${att.partner_name}: ${JSON.stringify(att.claims)}`));

// Trust score breakdown
const score = await client.getTrustScore('agent_id');
if (score.components) {
  console.log(`Transactions: ${score.components.receipt_score}`);
  console.log(`Counterparties: ${score.components.counterparty_score}`);
}

// Activity history
const activities = await client.getActivities('did:web:observerprotocol.org:agents:agent_id');

// DID document
const didDoc = await client.getDIDDocument('agent_id');
```

## Authentication

Most endpoints are public. Chain verification, audit writes, and extension registration require an API key:

```javascript
// Public (no key needed)
const client = new ObserverClient();
const agent = await client.getAgent('agent_id');

// Authenticated (key required)
const authClient = new ObserverClient({ apiKey: 'your_api_key' });
const result = await authClient.verifyLightningPayment({ ... });
```

To get an API key, email [dev@observerprotocol.org](mailto:dev@observerprotocol.org).

## TypeScript

Full TypeScript definitions included (`index.d.ts`).

```typescript
import { ObserverClient, Agent, TrustScore, ChainVerification } from '@observer-protocol/sdk';
```

## Supported chains

| Chain | Method | Status |
|-------|--------|--------|
| Lightning | `verifyLightningPayment()` | Live |
| TRON | `verifyTronTransaction()` | Live |
| Stacks | `verifyChain({ chain: 'stacks', ... })` | Stub |

## Documentation

- [Developer Guide](https://github.com/observer-protocol/observer-protocol-spec/tree/master/docs/developer-guide)
- [API Reference](https://github.com/observer-protocol/observer-protocol-spec/blob/master/docs/developer-guide/api-reference.md)
- [AIP v0.5 Spec](https://github.com/observer-protocol/observer-protocol-spec/blob/master/docs/AIP_v0.5.md)

## License

MIT
