# Chain Verification

OP verifies that transactions actually occurred on-chain. The verification is chain-agnostic — one endpoint, multiple chains.

## Endpoint

```
POST /v1/chain/verify
Authorization: Bearer <api_key>
```

## Supported chains

| Chain | Status | Adapter |
|-------|--------|---------|
| `lightning` | Live | `LightningAdapter` — three-tier verification |
| `tron` | Live | `TronAdapter` — TronGrid verification |
| `stacks` | Stub | `StacksAdapter` — interface defined, implementation pending |

## Lightning verification — payer/payee asymmetry

Lightning has a fundamental verification asymmetry:

- **Payee (recipient):** Possession of the preimage proves payment receipt. The payee revealed the preimage to collect payment — the Lightning protocol guarantees this.
- **Payer (sender):** Possession of the preimage does NOT prove payment. Preimages can be obtained through probing, forwarding, or out-of-band sharing.

OP handles this with three verification tiers:

### Tier 1: Payee attestation (strongest)

The payee issues a signed `LightningPaymentReceipt` VC confirming they received the payment. The payer presents this alongside the preimage.

```json
{
  "chain_specific": {
    "payment_hash": "<hex>",
    "preimage": "<hex>",
    "presenter_role": "payer",
    "payee_attestation": {
      "credential": {
        "type": ["VerifiableCredential", "LightningPaymentReceipt"],
        "issuer": "did:web:...:agents:payee_id",
        "credentialSubject": {
          "id": "did:web:...:agents:payer_id",
          "payment": {
            "payment_hash": "<hex>",
            "preimage": "<hex>",
            "amount_msat": 10000,
            "settled_at": "2026-04-25T10:00:00Z"
          }
        },
        "proof": { ... }
      }
    }
  }
}
```

OP verifies: schema conformance, payment_hash match, preimage hash, Ed25519 signature against payee's DID.

### Tier 2: LND node query (medium)

If OP has access to an LND node (via `LND_HOST` environment), it queries the node for invoice settlement status.

```json
{
  "chain_specific": {
    "payment_hash": "<hex>",
    "preimage": "<hex>",
    "presenter_role": "payer"
  }
}
```

No payee attestation needed — the LND node confirms settlement directly.

### Tier 3: Preimage only (payee-side only)

The payee presents the preimage. Valid ONLY when the presenter IS the payee.

```json
{
  "chain_specific": {
    "payment_hash": "<hex>",
    "preimage": "<hex>",
    "presenter_role": "payee"
  }
}
```

### Decision matrix

| Presenter | Has preimage | Has payee attestation | LND access | Result |
|-----------|-------------|----------------------|------------|--------|
| Payee | Yes | N/A | Optional | **Verified** (Tier 3 or 2) |
| Payer | Yes | Yes (valid) | Optional | **Verified** (Tier 1) |
| Payer | Yes | No | Yes (settled) | **Verified** (Tier 2) |
| Payer | Yes | No | No | **Rejected** |
| Either | No | Any | Any | **Rejected** |

### Conflict resolution

When Tier 1 and Tier 2 disagree (payee attests received, LND says not settled), **Tier 1 wins** — LND sync delays are a known failure mode. The response includes `conflict_detected: true` and `lnd_sync_delay_suspected: true`.

## TRON verification

```json
{
  "chain": "tron",
  "chain_specific": {
    "tron_tx_hash": "<hex>",
    "network": "mainnet"
  }
}
```

OP verifies the transaction against TronGrid. Response includes confirmation count and TRONScan link.

## Stacks verification

```json
{
  "chain": "stacks",
  "chain_specific": {
    "tx_id": "<hex>"
  }
}
```

Currently returns: `"Stacks chain verification is not yet implemented."` The adapter interface is defined and ready for integration.

## Adding a new chain

Implement one `ChainAdapter`:

```python
class MyChainAdapter(ChainAdapter):
    chain = "mychain"

    def verify_transaction(self, transaction, chain_specific):
        # Chain-specific verification logic
        return ChainVerificationResult(verified=True, ...)

    def get_explorer_url(self, reference):
        return f"https://explorer.mychain.io/tx/{reference}"

    def to_vac_extension(self, result):
        return {"type": "mychain_verification_v1", ...}
```

No changes to the protocol, verify endpoint, or audit trail.

## Idempotency

The endpoint is idempotent on `receipt_reference`. Calling with the same reference returns the cached result with `idempotent_replay: true`. If the same reference is submitted with a different `chain`, the endpoint returns `409 chain_mismatch`.
