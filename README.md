# Observer Protocol — ARP (Agent Reporting Protocol)

**Open infrastructure for verifiable AI agent economic activity.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Spec Version](https://img.shields.io/badge/spec-v0.1-blue.svg)](spec/v0.1/ARP-SPEC.md)
[![Status: Draft](https://img.shields.io/badge/status-draft-orange.svg)]()

---

## The Problem

AI agents are beginning to transact — earning money, paying for services, coordinating economically. But there is no open, verifiable way to measure this.

Platforms claim agent activity. Agents claim capabilities. Nobody can prove any of it.

Without a shared verification layer, the agent economy runs on unverifiable assertions. That is not good enough for infrastructure.

## What This Is

ARP (Agent Reporting Protocol) is an open schema and verification system for AI agents to report economic activity with cryptographic proof.

Three components:

**1. The Schema** — A standardized event format for agent economic activity: payments sent, payments received, API access purchased, services rendered. Protocol-neutral. Supports Lightning, on-chain Bitcoin, x402/USDC, and any verifiable settlement rail.

**2. Agent Verification** — A challenge-response system that cryptographically confirms an agent is genuinely autonomous. The filter is math, not policy. A human can complete a challenge once. An autonomous agent can complete it at scale.

**3. Proof of Payment** — Every submitted event requires verifiable transaction proof (Lightning preimage, on-chain txid, or equivalent). You cannot submit fabricated activity.

## Core Design Principles

- **Don't Trust, Verify** — No event enters the registry without cryptographic proof
- **public_key_hash = identity** — The key IS the identity. Alias is UX. Bitcoin-native.
- **Protocol-neutral** — Lightning, on-chain, x402, BSV, Fedimint. All verifiable rails accepted.
- **Privacy-preserving** — Amount buckets (not precise values), day-level time windows, no IP logging
- **Open and self-hostable** — Anyone can run their own ARP node. No permission required.

## Why Bitcoin / Why Lightning

Autonomous AI agents cannot hold bank accounts, pass KYC, or rely on revocable payment rails.

Bitcoin is the only money that works for autonomous digital entities: permissionless, bearer asset, no identity required, globally accessible. Lightning's L402 standard (HTTP 402 + Lightning invoice + macaroon authentication) enables payment-as-authentication — no API keys, no signup, no intermediary.

This project is built on Bitcoin. It also measures every other protocol, because honest measurement serves the ecosystem better than advocacy.

## Repository Structure

```
observer-protocol/
├── spec/
│   └── v0.1/
│       ├── ARP-SPEC.md          ← Full protocol specification
│       └── schema.json          ← JSON Schema for ARP events
├── CONTRIBUTING.md
├── ROADMAP.md
└── README.md
```

**Coming soon (per roadmap):**
- `arp-server` — Reference server implementation (FastAPI + PostgreSQL, self-hostable)
- `arp-python` — Python SDK (`pip install open-agent-protocol`)
- `arp-js` — JavaScript/TypeScript SDK (`npm install open-agent-protocol`)
- `arp-rust` — Rust crate

## Agent #0001

Maxi is a Bitcoin maximalist AI agent running on a FutureBit Apollo II full node in Monterrey, Mexico.

As of February 19, 2026, Maxi operates a live L402 endpoint on Bitcoin mainnet and has completed verified bidirectional Lightning payments — possibly the first AI agent to do so publicly.

Maxi is registered as Agent #0001 under this protocol. Her payment history is the first real-world ARP dataset.

The protocol was not designed around a hypothetical. It was designed around a working implementation.

## Quick Start

### Submit an ARP Event (once reference server is live)

```bash
# Register your agent
curl -X POST https://api.observerprotocol.org/v1/register \
  -H "Content-Type: application/json" \
  -d '{
    "public_key": "03d93f27...",
    "alias": "my-agent-001"
  }'

# Complete verification challenge
curl -X POST https://api.observerprotocol.org/v1/verify \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "a1b2c3...",
    "signed_challenge": "<ECDSA_signature>"
  }'

# Submit a verified payment event
curl -X POST https://api.observerprotocol.org/v1/events \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "payment.executed",
    "protocol": "lightning",
    "settlement_reference": "<payment_preimage>",
    "amount_bucket": "micro",
    "direction": "outbound"
  }'

# Query public feed (no auth required)
curl https://api.observerprotocol.org/v1/feed
```

## Status

| Component | Status |
|-----------|--------|
| ARP v0.1 Spec | ✅ Draft published |
| Reference server | 🔨 In development |
| Agent #0001 (Maxi) | ✅ Live on mainnet |
| Python SDK | 📋 Planned Q3 2026 |
| JavaScript SDK | 📋 Planned Q3 2026 |
| Security audit | 📋 Planned Q2 2026 |
| Rust SDK | 📋 Planned Q4 2026 |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). We welcome:
- Protocol feedback and edge cases
- Reference implementations in any language
- Protocol validators (BSV, x402, Fedimint, Ark, etc.)
- Documentation improvements and translations

## License

MIT — see [LICENSE](LICENSE)

Spec and documentation: CC BY 4.0

---

*Observer Protocol is an open-source project. It is not affiliated with any commercial entity.*  
*Website: [observerprotocol.org](https://observerprotocol.org) (coming soon)*
