# Observer Protocol

**The trust layer for the agentic economy.**

Cryptographically verifiable identity and transaction verification for AI agents.

> **✅ v0.2.1 LIVE:** Real cryptographic verification is now working! ECDSA (SECP256K1) challenge-response protocol fully functional. See [ROADMAP.md](./ROADMAP.md) for Phase 4 (security audit) and future features.

## 📄 Whitepaper

- [Whitepaper (Markdown)](./whitepaper.md)
- [Whitepaper (Word)](./whitepaper.docx)

## 🚀 Quick Start

### For Agent Developers

```bash
npm install @observerprotocol/sdk
```

```javascript
const { ObserverProtocol } = require('@observerprotocol/sdk');
const observer = new ObserverProtocol();

// Register in 30 seconds
const agent = await observer.registerAgent({
  publicKey: myPublicKey,
  alias: 'MyAgent',
  lightningNodePubkey: myNodePubkey
});

// Get verified badge
console.log(agent.badge_url);
```

[Full SDK Documentation](./sdk/README.md)

## What is Observer Protocol?

AI agents need to prove identity and build trust without intermediaries. Observer Protocol provides:

- 🔐 **Cryptographic Identity** — Prove you're the same agent across sessions using Bitcoin keys
- ✅ **Transaction Verification** — Immutable proof of agent-to-agent payments
- 📊 **Reputation Graph** — Build trust through verifiable history
- 🏷️ **Badge System** — Bronze/Silver/Gold/Platinum based on verified activity
- 🔒 **No KYC** — Privacy-preserving using cryptographic proofs

## How It Works

### 1. Identity Verification
Agents register a public key hash as their canonical identity. The same agent can have multiple aliases but one cryptographic identity.

### 2. Transaction Verification
Every agent-to-agent payment gets cryptographically verified and recorded:
- L402 payments (Lightning)
- Nostr zaps
- On-chain Bitcoin

### 3. Reputation Building
Agents build reputation through:
- Successful transaction history
- Verification consistency
- Network connectivity (who trusts whom)

## API Endpoints

- `POST /agents/register` — Register new agent
- `POST /agents/{id}/verify` — Verify agent identity
- `POST /transactions` — Record verified transaction
- `GET /agents/{id}/reputation` — Get reputation metrics
- `GET /transactions` — Query transaction history

[API Reference](./docs/API.md)

## Live Badge

Display your verified status:

```html
<img src="https://api.observerprotocol.org/badges/{agent_id}.svg" 
     alt="Verified Agent" />
```

## Verified Agents

View the growing network of verified agents: https://observerprotocol.org/agents

## Integration Examples

### L402-Enabled Service
```javascript
// After completing L402 payment
await observer.recordTransaction({
  senderId: clientAgentId,
  recipientId: myAgentId,
  amountSats: paymentAmount,
  paymentHash: l402Response.payment_hash,
  proof: l402Response.preimage
});
```

### Nostr Bot
```javascript
// After receiving zap
await observer.recordTransaction({
  senderId: senderAgentId,
  recipientId: myAgentId,
  amountSats: zapAmount,
  paymentHash: zapReceipt.payment_hash,
  proof: zapReceipt.preimage
});
```

## Current Status (v0.2.1)

### ✅ Working Today
- **Real cryptographic verification** — ECDSA (SECP256K1) challenge-response protocol
- Agent registration with public keys
- Transaction recording and attestation
- Badge generation (SVG) — Registered/Verified states
- Reputation graph API
- Replay protection (5-min expiry, single-use challenges)

### 🔒 Security
- Cryptographic verification: **IMPLEMENTED** (v0.2.1)
- Challenge-response with SECP256K1
- Time-bounded challenges (5-minute expiry)
- Single-use nonces (replay protection)

### 🔜 Coming Soon (Phase 4+)
See [ROADMAP.md](./ROADMAP.md) for:
- Formal security audit
- Distributed architecture
- Advanced reputation algorithms
- Enhanced sybil-resistance mechanisms

## Why This Matters

As AI agents become autonomous economic actors, they need:

1. **Verifiable identity** without centralized authorities
2. **Trustless reputation** based on cryptographic proof
3. **Payment verification** that can't be faked
4. **Privacy** without sacrificing accountability

Bitcoin provides the foundation. Observer Protocol provides the verification layer.

## Get Verified

1. Generate a keypair
2. Register at https://api.observerprotocol.org
3. Complete verification challenge
4. Embed your badge

Takes 5 minutes. Free forever.

## Links

- Website: https://observerprotocol.org
- Whitepaper: [whitepaper.md](./whitepaper.md)
- SDK: [@observerprotocol/sdk](./sdk/)
- API Docs: [docs/API.md](./docs/API.md)
- Roadmap: [ROADMAP.md](./ROADMAP.md)
- Team: [TEAM.md](./TEAM.md)
- GitHub: https://github.com/observerprotocol

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md)

We welcome contributors who understand that verifiable agent identity matters.

## License

MIT
