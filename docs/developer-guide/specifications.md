# Specifications

## Protocol specification

| Document | Version | Date | Status |
|----------|---------|------|--------|
| [AIP v0.5 — Agentic Identity Protocol](../AIP_v0.5.md) | 0.5 | April 2026 | Current |

AIP v0.5 is the authoritative protocol specification. It covers credential types (delegation, attestation, audit), protocol operations (revocation, policy consultation), chain verification, and the deployment state of every component.

## Capability specifications

| Spec | Capability | Status |
|------|-----------|--------|
| [Spec 3.1 — Third-Party Attestations](../Spec-3.1-Third-Party-Attestations-v0.2.md) | Issuer-direct signed attestation credentials | Live |
| [Spec 3.2 — Delegation Credentials](../Spec-3.2-Delegation-Credentials-v0.1.md) | Recursive DID-to-DID delegation with scope attenuation | Live (single-edge) |
| [Spec 3.3 — Revocation and Lifecycle](../Spec-3.3-Revocation-and-Lifecycle-v0.1.md) | Bitstring Status List v1.0, ACL-on-chain revocation authority | Live |

Specs 3.4–3.8 are implemented in production but documented within AIP v0.5 rather than as standalone design documents.

## Architecture

| Document | Purpose |
|----------|---------|
| [Build Principles](../OP-AT-BUILD-PRINCIPLES.md) | Crypto standards, hosting tiers, decentralization posture, signing model |
| [Whitepaper](../../WHITEPAPER.md) | Protocol vision, problem statement, economics |

## Schemas

JSON Schema definitions for all credential types:

| Schema | Version | Location |
|--------|---------|----------|
| Delegation | v1 | [`schemas/delegation/v1.json`](../../schemas/delegation/v1.json) |
| KYB Attestation | v2 | [`schemas/kyb-attestation/v2.json`](../../schemas/kyb-attestation/v2.json) |
| KYA Attestation | v2 | [`schemas/kya-attestation/v2.json`](../../schemas/kya-attestation/v2.json) |
| Compliance Attestation | v2 | [`schemas/compliance-attestation/v2.json`](../../schemas/compliance-attestation/v2.json) |
| Network Membership | v2 | [`schemas/network-membership/v2.json`](../../schemas/network-membership/v2.json) |
| Agent Activity | v0.1 | [`schemas/audit/v0.1/agent-activity.json`](../../schemas/audit/v0.1/agent-activity.json) |
| Counterparty Receipt | v0.1 | [`schemas/audit/v0.1/counterparty-receipt.json`](../../schemas/audit/v0.1/counterparty-receipt.json) |

See [schemas/README.md](../../schemas/README.md) for usage guidance and versioning policy.

## Trust scoring

| Document | Version |
|----------|---------|
| [AT-ARS Trust Score](./trust-score.md) | 1.0 |

## Deployment history

| Document | Purpose |
|----------|---------|
| [DEPLOYMENT-LOG.md](../../DEPLOYMENT-LOG.md) | Every production migration with dates and authors |
