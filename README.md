# Observer Protocol

**The trust layer for the agentic economy.**

Cryptographically verifiable identity and transaction verification for AI agents.

> **🚧 MVP Status:** This project is in alpha/MVP stage. Core infrastructure works but cryptographic verification is currently a stub (accepts any non-empty signature). See [Current Limitations](#current-limitations) and [ROADMAP.md](./ROADMAP.md) for details.

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

## Current Limitations (MVP/Alpha)

We're building in public. Here's what works today vs. what's coming:

### ✅ Working Today
- Agent registration with public key hashes
- Transaction recording and querying
- Badge generation (SVG)
- Reputation graph API
- Basic verification flow

### 🚧 MVP Limitations
- **Cryptographic verification is a stub** — Currently accepts any non-empty signature. Real challenge-response verification is in development (Phase 2).
- **Single-server architecture** — Not yet distributed
- **No formal security audit** — Planned before v1.0
- **Small team** — See [TEAM.md](./TEAM.md)

### 🔜 Coming Soon
See [ROADMAP.md](./ROADMAP.md) for detailed timeline including:
- Real challenge-response cryptographic verification
- Replay protection
- Security audit
- Team transparency improvements

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
