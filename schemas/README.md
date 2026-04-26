# Observer Protocol — Credential Schemas

W3C JSON Schema definitions for all credential types in the Observer Protocol. These schemas validate the `credentialSubject` structure of Verifiable Credentials issued under AIP v0.5.

## Schema inventory

### Attestation schemas

Used by third-party issuers (Spec 3.1) to attest facts about agents and organizations.

| Schema | Current version | Use when |
|--------|----------------|----------|
| [kyb-attestation](kyb-attestation/) | **v2** | Issuing KYB (Know Your Business) attestations. Contains entity name, jurisdiction, provider, status, credential status for revocation. |
| [kya-attestation](kya-attestation/) | **v2** | Issuing KYA (Know Your Agent) attestations. Agent operational attestations. |
| [compliance-attestation](compliance-attestation/) | **v2** | Issuing compliance-related attestations (regulatory, licensing). |
| [network-membership](network-membership/) | **v2** | Attesting network or consortium membership. |

### Delegation schema

Used by delegators (Spec 3.2) to authorize agents.

| Schema | Current version | Use when |
|--------|----------------|----------|
| [delegation](delegation/) | **v1** | Issuing delegation credentials. Defines action scope, delegation scope, ACL, enforcement mode. |

### Audit schemas

Used by agents (Spec 3.4) to self-sign activity records and by counterparties to issue receipts.

| Schema | Current version | Use when |
|--------|----------------|----------|
| [agent-activity](audit/v0.1/agent-activity.json) | **v0.1** | Agent self-signs a record of its own activity (transaction, counterparty interaction). |
| [counterparty-receipt](audit/v0.1/counterparty-receipt.json) | **v0.1** | Counterparty confirms their side of a transaction (dual-source evidence). |
| [receipt-request](audit/v0.1/receipt-request.json) | **v0.1** | Agent requests a receipt from a counterparty (pull protocol). |
| [receipt-acknowledgment](audit/v0.1/receipt-acknowledgment.json) | **v0.1** | Counterparty acknowledges or rejects a receipt request. |

## Versioning

- **v1 → v2:** The v2 versions of attestation schemas add `credentialStatus` for revocation/suspension support (Spec 3.3). If you are issuing new credentials, **use v2**. v1 credentials remain valid but cannot be revoked via Bitstring Status List.
- **v0.1 (audit):** Initial audit credential schemas. These are newer than v1/v2 attestation schemas — the version reflects the audit trail's earlier design stage, not lower quality.

**Rule:** Breaking changes (removing required fields, changing types) require a new version. Non-breaking additions (new optional fields) are permitted within the same version.

## Schema URIs

Each schema has a `$id` field declaring its canonical URI:

```
https://observerprotocol.org/schemas/kyb-attestation/v2.json
https://observerprotocol.org/schemas/delegation/v1.json
https://schemas.observerprotocol.org/audit/v0.1/agent-activity.json
```

These URIs are referenced in the `credentialSubject` of issued credentials. Verifiers can fetch the schema to validate credential structure.

## Which spec defines which schema

| Schema | Defined by | Capability |
|--------|-----------|-----------|
| kyb-attestation | Spec 3.1 | Third-party attestations |
| kya-attestation | Spec 3.1 | Third-party attestations |
| compliance-attestation | Spec 3.1 | Third-party attestations |
| network-membership | Spec 3.1 | Third-party attestations |
| delegation | Spec 3.2 | Delegation credentials |
| agent-activity | Spec 3.4 | Audit trail |
| counterparty-receipt | Spec 3.4 | Audit trail |
| receipt-request | Spec 3.4 | Audit trail |
| receipt-acknowledgment | Spec 3.4 | Audit trail |

## For integrators building VAC extensions

If you're registering a custom VAC extension (e.g., reputation scores), your extension schema is registered via `/v1/vac/extensions/register` and hosted at `observerprotocol.org/schemas/extensions/<namespace>/v<version>`. Extension schemas follow the same JSON Schema format as the schemas in this directory. See [AIP v0.5 §4](../docs/AIP_v0.5.md) for the VAC extension protocol.
