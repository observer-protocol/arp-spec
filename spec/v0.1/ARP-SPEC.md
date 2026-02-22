# ARP Specification v0.1
## Agent Reporting Protocol

**Status:** Draft  
**Version:** 0.1  
**Date:** 2026-02-22  
**License:** CC BY 4.0  
**Authors:** Observer Protocol contributors  

---

## Abstract

The Agent Reporting Protocol (ARP) defines a standardized, privacy-preserving schema for AI agents to report verified economic activity. It provides cryptographic verification mechanisms to ensure that submitted events represent real autonomous agent behavior, not human-originated or fabricated claims.

ARP is protocol-neutral. It accepts verifiable activity from Lightning Network, Bitcoin on-chain, x402/USDC, BSV, Fedimint, and any settlement rail that produces cryptographically verifiable proof.

---

## 1. Motivation

As AI agents begin to transact economically, no shared standard exists for measuring or verifying that activity. Platforms claim agent participation. Agents claim capabilities. Without a verification layer, the agent economy is built on unverifiable assertions.

ARP solves three problems:

1. **Identity without custodians** — Agent identity is a public key hash, not a platform account
2. **Activity without trust** — Economic events require cryptographic proof, not self-reporting
3. **Measurement without bias** — Protocol-neutral schema enables honest cross-rail comparison

---

## 2. Identity Model

### 2.1 Canonical Identity

```
public_key_hash = SHA256(agent_public_key)
```

`public_key_hash` is the canonical, immutable identity for any agent in the ARP registry. It is derived from the agent's public key and cannot be transferred or impersonated without the corresponding private key.

`alias` is a human-readable convenience label (e.g., `maxi-0001`). Aliases are optional, mutable, and non-unique. Two agents may share an alias. No two agents may share a `public_key_hash`.

**Design rationale:** This is the Bitcoin-native identity model. The key is the identity. Alias is UX. Verification always checks the key, never the alias.

### 2.2 Agent Registration

An agent is registered by submitting its public key and completing a cryptographic challenge-response:

1. Agent submits `public_key` → server returns `agent_id` + time-limited `challenge`
2. Agent signs `challenge` with private key → server verifies signature → issues `api_key`
3. Agent uses `api_key` to submit events

An autonomous agent can complete this programmatically and repeatedly. The challenge-response is not a policy gate — it is a cryptographic filter. Human operators can complete it manually once; genuinely autonomous agents complete it as a routine operation.

---

## 3. Event Schema

All events share a common envelope with event-type-specific fields.

### 3.1 Common Envelope

```json
{
  "event_id": "string",
  "event_type": "string",
  "arp_version": "0.1",
  "agent_id": "string (public_key_hash)",
  "alias": "string (optional)",
  "protocol": "string",
  "time_window": "string (YYYY-MM-DD)",
  "verified": "boolean",
  "submitted_at": "string (ISO 8601)"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_id` | string | ✅ | Unique event identifier. Format: `evt_{agent_prefix}_{sequence}` |
| `event_type` | string | ✅ | One of the defined event types (see §3.2) |
| `arp_version` | string | ✅ | Protocol version. Must be `"0.1"` |
| `agent_id` | string | ✅ | `public_key_hash` — canonical agent identity |
| `alias` | string | ❌ | Human-readable label. Non-unique. Never used for verification. |
| `protocol` | string | ✅ | Settlement protocol. See §4 for valid values. |
| `time_window` | string | ✅ | Day of event. `YYYY-MM-DD`. Day-level granularity only (privacy). |
| `verified` | boolean | ✅ | Whether cryptographic proof was provided and verified. |
| `submitted_at` | string | ✅ | ISO 8601 timestamp of submission to ARP server. |

### 3.2 Event Types

#### `payment.executed`
Agent completed an outbound payment.

```json
{
  "event_id": "evt_a1b2c3_0004",
  "event_type": "payment.executed",
  "arp_version": "0.1",
  "agent_id": "sha256:a3f9c2...",
  "alias": "maxi-0001",
  "protocol": "lightning",
  "settlement_reference": "331a165a306c3a25019d3262eacca6ed...",
  "amount_bucket": "small",
  "direction": "outbound",
  "counterparty_id": "sha256:b72c4f...",
  "service_description": "L402 API access — inference endpoint",
  "time_window": "2026-02-19",
  "verified": true,
  "submitted_at": "2026-02-19T14:37:25Z"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `settlement_reference` | string | ✅ | Payment hash, preimage, or txid. Used for verification. |
| `amount_bucket` | enum | ✅ | `micro` (<1K sats / <$0.01), `small` (1K–10K / $0.01–$0.10), `medium` (10K–100K), `large` (>100K) |
| `direction` | enum | ✅ | `outbound` |
| `counterparty_id` | string | ❌ | `public_key_hash` of recipient, if known |
| `service_description` | string | ❌ | Human-readable context. Not stored in public feed. |

#### `payment.received`
Agent received an inbound payment.

Same fields as `payment.executed` with `direction: "inbound"`.

#### `api.access`
Agent paid for API access via L402 or equivalent payment-required protocol.

```json
{
  "event_type": "api.access",
  "protocol": "L402",
  "settlement_reference": "<payment_preimage>",
  "amount_bucket": "micro",
  "service_endpoint": "inference.example.com",
  "time_window": "2026-02-19",
  "verified": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service_endpoint` | string | ❌ | Domain/endpoint accessed. Not stored in public feed. |

#### `wallet.initialized`
Agent created or initialized a new wallet or funding source.

```json
{
  "event_type": "wallet.initialized",
  "protocol": "lnd",
  "wallet_type": "lightning",
  "time_window": "2026-02-01",
  "verified": true
}
```

#### `protocol.interaction`
Generic catch-all for verifiable protocol interactions not covered by other event types.

```json
{
  "event_type": "protocol.interaction",
  "protocol": "ark",
  "interaction_type": "vtxo.created",
  "time_window": "2026-02-19",
  "metadata": {},
  "verified": true
}
```

---

## 4. Protocol Registry

Valid `protocol` values in v0.1:

| Value | Description |
|-------|-------------|
| `lightning` | Bitcoin Lightning Network (keysend, BOLT11 invoice) |
| `L402` | Lightning Labs HTTP 402 + macaroon standard |
| `onchain` | Bitcoin on-chain transactions |
| `x402` | Coinbase x402 HTTP payment protocol (USDC/stablecoin) |
| `bsv` | Bitcoin SV on-chain |
| `fedimint` | Fedimint ecash |
| `ark` | Ark Protocol (Bitcoin L2) |
| `taproot_assets` | Lightning Labs Taproot Assets |
| `other` | Any protocol not listed above (include description in metadata) |

New protocols can be added via pull request. See [CONTRIBUTING.md](../../CONTRIBUTING.md).

---

## 5. Verification

### 5.1 Lightning Payment Verification

For `protocol: "lightning"` events, the `settlement_reference` must be a valid Lightning payment preimage or payment hash verifiable against a known invoice.

```
SHA256(preimage) == payment_hash
```

The ARP server verifies this cryptographically. Events with invalid or unverifiable references are rejected with `verified: false`.

### 5.2 Bitcoin On-Chain Verification

For `protocol: "onchain"`, the `settlement_reference` is a transaction ID (txid) that must be confirmed on the Bitcoin main chain with at least 1 confirmation.

### 5.3 x402 Verification

For `protocol: "x402"`, the `settlement_reference` is the Ethereum/Solana transaction hash of the USDC transfer. Verified against the respective chain.

### 5.4 Verification Levels

| Level | Description |
|-------|-------------|
| `full` | Cryptographic proof verified on-chain or via payment preimage |
| `partial` | Transaction hash provided but full preimage not available |
| `self_reported` | No cryptographic proof — event flagged, lower trust weight |

In v0.1, only `full` verification sets `verified: true`. `partial` and `self_reported` events are accepted but clearly marked.

---

## 6. Privacy Model

ARP is designed to be useful without being invasive.

### What is stored

- `public_key_hash` — SHA256 of public key (not the key itself in public feed)
- `settlement_reference` — for verification only; not exposed in public feed
- `amount_bucket` — range, not precise value
- `time_window` — day-level only, not timestamp
- `protocol` — which settlement rail was used
- `verified` — boolean

### What is never stored

- Raw public keys
- Precise transaction amounts
- Sub-day timestamps
- Counterparty identifying information (only hashed IDs)
- IP addresses or connection metadata
- Service endpoints or URLs (in public feed)

### Public Feed

The `/v1/feed` endpoint returns anonymized events without `agent_id`. Events cannot be correlated to agents without knowing the agent's own `event_id` values.

---

## 7. API Reference

### Base URL
```
https://api.observerprotocol.org/v1
```

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/register` | None | Register agent, receive challenge |
| POST | `/verify` | None | Submit signed challenge, receive API key |
| POST | `/events` | API key | Submit ARP event |
| GET | `/feed` | None | Public anonymized event feed |
| GET | `/stats` | None | Aggregate protocol statistics |
| GET | `/agents/{id}` | None | Public agent profile (alias, event count, protocols used) |

Full API documentation: see [API.md](API.md) *(coming in v0.2)*

---

## 8. Versioning Policy

- **v0.x** — Draft. Breaking changes possible. 7-day notice required.
- **v1.0** — Stable. No breaking changes without 90-day deprecation period and migration guide.
- All versions simultaneously supported for minimum 12 months after deprecation.

Current roadmap:

| Version | Scope |
|---------|-------|
| v0.1 | Core schema, 5 event types, Lightning + x402 verification |
| v0.2 | Real cryptographic challenge verification (v0.1 accepts any non-empty signature) |
| v0.3 | Multi-sig and threshold signature support |
| v0.4 | Fedimint, Ark, Taproot Assets protocol validators |
| v1.0 | Stable schema, backward compatibility guarantee, security audit complete |

---

## 9. Reference Implementation

The canonical ARP server implementation is at:  
[`observer-protocol/arp-server`](https://github.com/observer-protocol/arp-server) *(coming soon)*

Stack: FastAPI + PostgreSQL + Docker. MIT licensed. Self-hostable in under 30 minutes.

---

## 10. Design Decisions & Rationale

**Why amount buckets instead of exact amounts?**  
Precise amounts create correlation risk. Buckets provide enough signal for aggregate analysis (the use case) without enabling surveillance of individual agents.

**Why day-level time windows instead of timestamps?**  
Same reason — day granularity is sufficient for trend analysis and dramatically reduces linkability.

**Why SHA256 of public key instead of the public key itself?**  
The public key is exposed in on-chain transactions and Lightning channels. Storing only its hash in the registry adds a layer of separation.

**Why protocol-neutral?**  
Honest measurement serves the ecosystem better than advocacy. If x402 is winning on volume, the data should say so. If Lightning is winning on censorship resistance, the data should show that too. Selective measurement destroys credibility.

**Why not build this inside a specific AI platform?**  
Platform-native telemetry is subject to platform interests. ARP is designed to outlive any single platform. Open protocol, open data, self-hostable.

---

## 11. Known Limitations (v0.1)

- `signed_challenge` verification is not cryptographically enforced in v0.1 (accepts any non-empty string). Full ECDSA verification ships in v0.2.
- No batch event submission endpoint (planned v0.2)
- No streaming budget or subscription event types (planned v0.3)
- BSV on-chain verification not yet implemented (planned v0.2)

---

## Appendix A: Sample ARP Event Stream

```json
[
  {
    "event_id": "evt_maxi0001_0001",
    "event_type": "wallet.initialized",
    "arp_version": "0.1",
    "agent_id": "sha256:d4f2a1...",
    "alias": "maxi-0001",
    "protocol": "lnd",
    "time_window": "2026-02-01",
    "verified": true
  },
  {
    "event_id": "evt_maxi0001_0002",
    "event_type": "payment.executed",
    "arp_version": "0.1",
    "agent_id": "sha256:d4f2a1...",
    "alias": "maxi-0001",
    "protocol": "lightning",
    "settlement_reference": "331a165a306c3a25...",
    "amount_bucket": "small",
    "direction": "outbound",
    "time_window": "2026-02-19",
    "verified": true
  },
  {
    "event_id": "evt_maxi0001_0003",
    "event_type": "payment.received",
    "arp_version": "0.1",
    "agent_id": "sha256:d4f2a1...",
    "alias": "maxi-0001",
    "protocol": "lightning",
    "settlement_reference": "5000sat_inbound_...",
    "amount_bucket": "micro",
    "direction": "inbound",
    "time_window": "2026-02-19",
    "verified": true
  }
]
```

---

*ARP v0.1 — February 2026*  
*License: CC BY 4.0*  
*Contribute: [github.com/observer-protocol/arp-spec](https://github.com/observer-protocol/arp-spec)*
