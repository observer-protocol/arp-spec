# Observer Protocol

**The trust layer for the agentic economy.**

Cryptographically verifiable identity and transaction verification for AI agents.

> **✅ v0.3.0 LIVE:** Production-ready with full security audit! Transaction signatures, VAC credentials, and verified attestation — all cryptographically secured. See [ROADMAP.md](./ROADMAP.md) for upcoming features.

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
- ✅ **Transaction Verification** — Immutable proof of agent-to-agent payments with signature validation
- 📊 **Reputation Graph** — Build trust through verifiable history
- 🏷️ **Badge System** — Bronze/Silver/Gold/Platinum based on verified activity
- 🔒 **No KYC** — Privacy-preserving using cryptographic proofs

## Security Features

### Transaction Signature Verification (v0.3.0)

All transactions are cryptographically signed by the sending agent:

**Signing Format:**
```
agent_id:transaction_reference:protocol:timestamp
```

**Example:**
```
agent-001:tx-12345:lightning:1712345678
```

The server verifies:
1. Agent is registered and verified
2. Transaction signature matches agent's public key
3. Message format is canonical (no tampering)

Invalid signatures are rejected with HTTP 400.

### VAC (Verifiable Agent Credentials)

VAC credentials provide cryptographic proof of agent activity:

```json
{
  "agent_id": "agent-001",
  "public_key_hash": "a1b2c3...",
  "verified_tx_count": 42,
  "unique_counterparties": 8,
  "last_activity": "2024-03-26T20:00:00Z",
  "issued_at": "2024-03-26T20:05:00Z",
  "expires_at": "2024-06-24T20:05:00Z",
  "signature": "..."
}
```

VACs are signed by the Observer Protocol authority and can be verified by any third party.

## How It Works

### 1. Identity Verification
Agents register a public key hash as their canonical identity. The same agent can have multiple aliases but one cryptographic identity.

### 2. Transaction Verification
Every agent-to-agent payment gets cryptographically verified and recorded:
- L402 payments (Lightning)
- Nostr zaps
- On-chain Bitcoin
- Cross-protocol settlements (x402, Solana)

### 3. Reputation Building
Agents build reputation through:
- Successful transaction history
- Verification consistency
- Network connectivity (who trusts whom)

## API Endpoints

### Agent Management
- `POST /observer/agents/register` — Register new agent
- `GET /observer/agents/{pubkey}/verify` — Check agent verification status
- `GET /observer/agents/list` — List all registered agents
- `GET /observer/agents/{pubkey}/transactions` — Get agent transaction history

### Transaction Recording
- `POST /observer/transactions` — Submit verified transaction (requires signature)
- `GET /observer/transactions` — Query transaction history

### VAC Credentials
- `GET /observer/agents/{pubkey}/vac` — Get Verifiable Agent Credential
- `POST /observer/agents/{pubkey}/vac/verify` — Verify VAC signature

### Registry
- `GET /observer/trends` — Get network-wide statistics
- `GET /observer/agents/{pubkey}/delegations` — Get agent delegations

[Full API Reference](./docs/API.md)

## Live Badge

Display your verified status:

```html
<img src="https://api.agenticterminal.ai/observer/badges/{agent_id}.svg" 
     alt="Verified Agent" />
```

## Verified Agents

View the growing network of verified agents: https://observerprotocol.org/registry.html

## Integration Examples

### L402-Enabled Service
```javascript
// After completing L402 payment
await observer.recordTransaction({
  senderId: clientAgentId,
  recipientId: myAgentId,
  amountSats: paymentAmount,
  paymentHash: l402Response.payment_hash,
  protocol: 'lightning',
  signature: mySignature // Sign: senderId:paymentHash:lightning:timestamp
});
```

### Webhook Integration
```javascript
// Receive real-time verification events
observer.on('transaction:verified', (tx) => {
  console.log(`Payment verified: ${tx.amountSats} sats from ${tx.senderId}`);
  // Grant access, update reputation, etc.
});
```

## Architecture

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│   Agent A   │────→│  L402/x402      │────→│   Agent B   │
│  (Sender)   │     │  Payment Rail   │     │ (Recipient) │
└─────────────┘     └─────────────────┘     └─────────────┘
        │                                          │
        │    ┌──────────────────────────────┐     │
        └───→│  Observer Protocol Verify    │←────┘
             │  • Cryptographic identity    │
             │  • Transaction attestation   │
             │  • Reputation graph          │
             └──────────────────────────────┘
```

## Protocol Support

| Protocol | Status | Description |
|----------|--------|-------------|
| L402 | ✅ Live | Lightning-native payments |
| x402 | ✅ Live | HTTP 402 payment standard |
| Nostr | ✅ Live | Zap verification |
| Solana | 🔄 Beta | Program signatures |
| ERC-8004 | 🔄 Beta | EVM agent registry |

## Roadmap

See [ROADMAP.md](./ROADMAP.md) for detailed phase breakdown.

- ✅ **Phase 1:** Core infrastructure
- ✅ **Phase 2:** Lightning integration
- ✅ **Phase 3:** Multi-protocol support
- ✅ **Phase 4:** Security audit & production hardening
- 🔄 **Phase 5:** Partnership integrations
- ⏳ **Phase 6:** Decentralized verification

## Contributing

We welcome contributions! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](./LICENSE) for details.

## Links

- Website: https://observerprotocol.org
- Registry: https://observerprotocol.org/registry.html
- Docs: https://observerprotocol.org/docs
- Twitter: [@Obsrver_Prtcl](https://twitter.com/Obsrver_Prtcl)
- GitHub: https://github.com/observer-protocol

---

**Built for the agentic economy.** 🔐⚡
