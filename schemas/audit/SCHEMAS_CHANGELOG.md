# Audit Schemas Changelog

## v0.1 — 2026-04-23

Initial version. Covers observed transaction activity between known parties.

**4 credential types:**
- `AgentActivityCredential` — agent-signed activity record (individual or Merkle root)
- `CounterpartyReceiptCredential` — counterparty-signed receipt of agent activity
- `ReceiptRequestCredential` — agent-signed pull-protocol request for a receipt
- `ReceiptAcknowledgment` — counterparty-signed response to a receipt request

**Extensibility (per Leo's review):**
- `credentialSubject.additionalProperties: true` — future fields don't break v0.1
- `@context` array tolerates additional URLs beyond the v0.1 namespace
- `type` array tolerates additional type identifiers
- `proof.type` is not enum-restricted — future proof suites accepted
- Top-level `additionalProperties: false` for structural correctness

**Scope boundary:**
- v0.1 does NOT cover delegation credentials, org attestations, or KYB/compliance
- Those types use the same extensibility mechanisms when they ship
- v0.1 URLs remain stable forever; breaking changes go to v0.2+

**Published at (pending website publish — local validation active, public URL deferred):**
- `https://schemas.observerprotocol.org/audit/v0.1/agent-activity.json`
- `https://schemas.observerprotocol.org/audit/v0.1/counterparty-receipt.json`
- `https://schemas.observerprotocol.org/audit/v0.1/receipt-request.json`
- `https://schemas.observerprotocol.org/audit/v0.1/receipt-acknowledgment.json`
