# Architecture Overview

## The problem OP solves

Autonomous agents transact across chains, platforms, and jurisdictions. No single chain or platform can verify an agent's full activity history, delegation authority, or trustworthiness. The result: agents build siloed reputation that doesn't travel, counterparties can't verify claims, and agent commerce has no trust substrate.

Observer Protocol is that trust substrate.

## Protocol layers

```
┌─────────────────────────────────────────┐
│         Policy Engine                   │  Pre-commit checks (fail-closed)
├─────────────────────────────────────────┤
│      AIP — Agentic Identity Protocol    │  Delegation, attestation, audit,
│                                         │  revocation, policy consultation
├─────────────────────────────────────────┤
│    OP — Observer Protocol               │  DIDs, VAC, schemas, status lists
├─────────────────────────────────────────┤
│        Settlement Rails                 │  Lightning, TRON, Stacks, x402
└─────────────────────────────────────────┘
```

### OP — Observer Protocol (foundation)

The identity and credential layer. Every agent and organization gets a W3C Decentralized Identifier (`did:web`), publicly resolvable. Credentials are W3C Verifiable Credentials (VC Data Model 2.0) signed with Ed25519.

OP hosts schemas, DID documents, and credential status lists. OP does not custody keys or store agent activity logs.

### AIP — Agentic Identity Protocol (protocol)

The protocol layer governing what agents can do and what evidence exists about what they've done. AIP defines three credential types and two operations:

**Credential types:**

| Type | Purpose | Issued by |
|------|---------|-----------|
| Delegation Credential | "Agent X is authorized to spend up to $50 on AI inference by Human Y" | The delegator (human, org, or parent agent) |
| Attestation Credential | "Agent X passed KYB verification with MoonPay" | The attesting party (partner, verifier, counterparty) |
| Audit Credential | "Agent X executed this Lightning payment at this time" | The agent itself (self-signed activity record) |

**Operations:**

| Operation | Purpose |
|-----------|---------|
| Revocation & Lifecycle | Invalidate or suspend any credential via Bitstring Status List v1.0 |
| Policy Consultation | Pre-commit check: "Should this action proceed?" Fail-closed by default. |

### VAC — Verified Agent Credential

The VAC is OP's identity credential for an agent. It certifies that the agent is registered and links to the agent's delegation credentials, attestation credentials, and third-party extensions.

The VAC is a static identity certificate — it does not contain transaction history or trust scores. Those live in the audit trail (agent-issued) and trust scoring layer (AT-computed, surfaced as a VAC extension).

### Settlement Rails

OP is chain-agnostic. Transaction verification is handled by chain-specific adapters (`ChainAdapter` interface). Currently supported:

- **Lightning** — three-tier verification with payer/payee asymmetry
- **TRON** — TronGrid verification for TRC-20 transactions
- **Stacks** — interface defined, adapter implementation pending

Adding a chain means implementing one adapter. No protocol changes required.

## Cryptographic standards

| Standard | Usage |
|----------|-------|
| W3C DID (did:web) | All identities |
| W3C VC Data Model 2.0 | All credentials |
| Ed25519Signature2020 | All credential proofs |
| Bitstring Status List v1.0 | Credential revocation and suspension |

All credentials are independently verifiable: resolve the issuer's DID, extract the public key, verify the Ed25519 signature. No runtime dependency on OP.

## Key architectural principles

1. **OP hosts bytes, never keys, never event logs.** Agent activity records are agent-issued. OP provides the schema and the DID; consuming services ingest the evidence.
2. **Issuer-direct signing.** The party making the claim signs the credential. No intermediaries.
3. **One credential type for delegation.** No type hierarchy. "Org-to-agent" and "human-to-agent" are the same primitive with different usage patterns.
4. **Three-tier hosting.** OP hosts schemas and DIDs. AT/service layer hosts enterprise state and policy engines. Agents hold their own credentials.
5. **Chain-agnostic from day one.** Every endpoint that touches transaction data uses the `ChainAdapter` interface, not chain-specific logic.

## Full specification

The complete protocol specification is [AIP v0.5](../AIP_v0.5.md).
