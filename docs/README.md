# Observer Protocol — Documentation Index

## Protocol specification

| Document | Version | What it covers |
|----------|---------|---------------|
| [AIP v0.5](AIP_v0.5.md) | 0.5 (Apr 25, 2026) | **Start here.** The Agentic Identity Protocol — credential types, protocol operations, deployment state. Supersedes v0.3.1. |
| [Build Principles](OP-AT-BUILD-PRINCIPLES.md) | 0.1 (Apr 21, 2026) | Architectural decisions: crypto standards, hosting tiers, decentralization posture, signing model. |

## Capability specifications

Read in order. Each spec builds on the previous.

| Spec | Capability | What it defines | Status |
|------|-----------|----------------|--------|
| [Spec 3.1](Spec-3.1-Third-Party-Attestations-v0.2.md) | Third-party attestations | Issuer-direct signed W3C VCs. Partner registry. KYB as verifiable credential. | Live |
| [Spec 3.2](Spec-3.2-Delegation-Credentials-v0.1.md) | Delegation credentials | Recursive DID-to-DID authorization. Scope attenuation. ACL per edge. One credential type, no hierarchy. | Live (single-edge) |
| [Spec 3.3](Spec-3.3-Revocation-and-Lifecycle-v0.1.md) | Revocation & lifecycle | Bitstring Status List v1.0. Revocation (terminal) + suspension (reversible). ACL-on-chain authority model. | Live |
| Spec 3.4 | Audit trail | Dual-source evidence: agent activity credentials + counterparty receipts. Incremental Merkle tree. | Live (migration 010) |
| Spec 3.5 | Policy consultation | Pre-commit policy checks. One engine per org. Fail-closed. Signed decisions. | Live (migration 013) |
| Spec 3.6 | Counterparty management | Auto-discovery from transactions. Org-level acceptance lifecycle. Policy context enrichment. | Live (migration 014) |
| Spec 3.7 | Agent profile | Agent configuration and metadata management. | Live |
| Spec 3.8 | SSO & human identity | SAML SSO. Human principals as DIDs. Per-org IdP configuration. | Live (migrations 011–012) |

**Note:** Specs 3.4–3.8 are implemented (see [DEPLOYMENT-LOG.md](../DEPLOYMENT-LOG.md)) but do not yet have standalone design documents. The implementation is the spec. AIP v0.5 covers their protocol-level design.

## Reference

| Document | Purpose |
|----------|---------|
| [VAC-CHAIN-DEPENDENCIES.md](VAC-CHAIN-DEPENDENCIES.md) | Credential chain dependencies and verification ordering |
| [DEPLOYMENT-LOG.md](../DEPLOYMENT-LOG.md) | What's deployed in production and when |
| [REPO_MAP.md](../REPO_MAP.md) | Repository navigation — what lives here vs. sibling repos |
| [WHITEPAPER.md](../WHITEPAPER.md) | Protocol vision and economics (v1.0, March 2026) |

## Demos and build history

Historical demo runbooks and build logs are archived in [docs/demos/](demos/) and [archive/](../archive/).

| Document | Context |
|----------|---------|
| [4Act Demo API Reference](demos/API-QUICK-REF-4Act-Demo.md) | TRON 4-agent demo endpoints |
| [4Act Demo Runbook](demos/RUNBOOK-Sam-4Act-TRON-Demo.md) | Operational runbook for TRON demo |
| [4Act BD Summary](demos/BD-SUMMARY-4Act-Demo.md) | Business development context |
