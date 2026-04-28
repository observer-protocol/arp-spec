# OP Chargeback Prevention Demo — Technical Runbook

**Version:** 1.0
**Date:** 2026-04-27
**Status:** Phase 1 schema lock complete

---

## Beat-by-beat flow with protocol details

### Beat 1 — Agent attempts purchase

**Actor:** Maxi (agent `d13cdfceaa8f895afe56dc902179d279`)

1. Maxi queries NeuralBridge's payment configuration endpoint:
   ```
   GET https://api.neuralbridge.ai/payment-config
   ```
   Response:
   ```json
   {
     "counterparty_did": "did:web:neuralbridge.ai",
     "counterparty_name": "NeuralBridge",
     "accepted_rails": ["usdt-trc20", "lightning"],
     "products": [
       {
         "id": "gpu-credits-500",
         "name": "GPU Inference API Credits (500 units)",
         "price": "50.00",
         "currency": "USDT"
       }
     ]
   }
   ```

2. Maxi evaluates rail selection (per her runtime policy):
   - Policy: prefer `usdt-trc20`, fallback `lightning`
   - NeuralBridge accepts both → selects `usdt-trc20`

3. Maxi submits purchase request:
   ```
   POST https://api.neuralbridge.ai/purchase
   Content-Type: application/json

   {
     "agent_did": "did:web:observerprotocol.org:agents:d13cdfceaa8f895afe56dc902179d279",
     "product_id": "gpu-credits-500",
     "rail": "usdt-trc20",
     "amount": "50.00",
     "currency": "USDT"
   }
   ```

### Beat 2 — Soft reject and magic link

**Actor:** NeuralBridge verification stack

NeuralBridge's verification stack checks for a delegation credential. None present. Returns AIP-shaped soft-reject:

```json
{
  "verdict": "soft_rejected",
  "reason": "no_delegation_credential",
  "magic_link": {
    "url": "https://sovereign.agenticterminal.io/authorize?token=eyJhbGciOiJFZERTQSIs...",
    "intro": "I tried to purchase $50.00 in GPU inference API credits from NeuralBridge and need your authorization. Tap here to approve:",
    "transaction_context": {
      "counterparty": "NeuralBridge",
      "counterparty_did": "did:web:neuralbridge.ai",
      "amount": "50.00",
      "currency": "USDT",
      "rail": "usdt-trc20",
      "purchase_description": "GPU Inference API Credits (500 units)"
    },
    "expires_at": "2026-04-28T15:45:00Z"
  }
}
```

Maxi receives the soft-reject and forwards the magic link to Boyd via her configured human-comms channel. The message Boyd sees:

> I tried to purchase $50.00 in GPU inference API credits from NeuralBridge and need your authorization.
>
> Tap here to approve: [link]
>
> Expires in 15 minutes.

### Beat 3 — Boyd opens magic link

**Actor:** Boyd (principal `df9005aa4387282c121affac188fab9f`)

Boyd taps the link on his phone. Lands on Sovereign authorization page at:
```
https://sovereign.agenticterminal.io/authorize?token=<signed-jwt>
```

The page decodes the JWT, verifies the signature, and renders:

> **Maxi is requesting to purchase $50.00 in API credits from NeuralBridge, to be settled in USDT on TRON.**

Three options presented:

1. **Approve once** (default, visually highlighted) — single click
2. **Approve recurring with NeuralBridge** — sliders for ceiling, period, expiration
3. **Set up broader policy** — links to Sovereign policy configuration

Boyd clicks **Approve once**.

**Mobile requirement:** This page must be fully functional at 375px viewport width. The "Approve once" path must complete in 3 clicks or fewer and under 30 seconds.

### Beat 4 — Delegation credential issued and pushed

**Actor:** Sovereign

Sovereign signs a Level 1 (one-time) delegation credential:

```json
{
  "@context": ["https://www.w3.org/ns/credentials/v2", "https://observerprotocol.org/context/delegation/v2"],
  "id": "urn:uuid:delegation-<uuid>",
  "type": ["VerifiableCredential", "DelegationCredential"],
  "issuer": "did:web:sovereign.agenticterminal.io:users:df9005aa4387282c121affac188fab9f",
  "validFrom": "2026-04-28T15:31:00Z",
  "validUntil": "2026-04-28T15:46:00Z",
  "credentialSubject": {
    "id": "did:web:observerprotocol.org:agents:d13cdfceaa8f895afe56dc902179d279",
    "authorizationLevel": "one-time",
    "authorizationConfig": {
      "oneTime": {
        "counterparty_did": "did:web:neuralbridge.ai",
        "amount": "50.00",
        "currency": "USDT",
        "rail": "usdt-trc20",
        "execution_deadline": "2026-04-28T15:46:00Z",
        "purchase_description": "GPU Inference API Credits (500 units)"
      }
    },
    "actionScope": {
      "allowed_rails": ["usdt-trc20"],
      "per_transaction_ceiling": { "amount": "50.00", "currency": "USDT" },
      "allowed_transaction_categories": ["ai_inference_credits"]
    },
    "delegationScope": { "may_delegate_further": false },
    "enforcementMode": "pre_transaction_check"
  },
  "credentialSchema": {
    "id": "https://observerprotocol.org/schemas/delegation/v2.json",
    "type": "JsonSchema"
  },
  "proof": {
    "type": "Ed25519Signature2020",
    "created": "2026-04-28T15:31:00Z",
    "verificationMethod": "did:web:sovereign.agenticterminal.io:users:df9005aa4387282c121affac188fab9f#key-1",
    "proofPurpose": "assertionMethod",
    "proofValue": "z..."
  }
}
```

The signed credential is delivered to Maxi via agent infrastructure — not through the human-comms channel. Sovereign publishes the credential to a retrieval endpoint; Maxi polls or receives a webhook callback to collect it. Human-comms channels (WhatsApp, Telegram, etc.) carry human-readable messages; signed VCs travel over agent-to-service infrastructure.

**Timing:** Total elapsed from Beat 2 to here must be visibly under 30 seconds in the demo recording.

### Beat 5 — Agent retries, settlement happens

**Actor:** Maxi

Maxi retries the purchase with the credential attached:

```
POST https://api.neuralbridge.ai/purchase
Content-Type: application/json

{
  "agent_did": "did:web:observerprotocol.org:agents:d13cdfceaa8f895afe56dc902179d279",
  "product_id": "gpu-credits-500",
  "rail": "usdt-trc20",
  "amount": "50.00",
  "currency": "USDT",
  "delegation_credential": { ... full signed VC ... }
}
```

NeuralBridge verification:
1. Verify Ed25519 signature against issuer's published public key
2. Confirm `authorizationLevel` is `one-time` and scope covers this exact transaction
3. Confirm `validFrom <= now < validUntil`
4. Confirm counterparty_did matches NeuralBridge's own DID
5. Accept settlement

USDT-on-TRON transaction executes on-chain.

### Beat 6 — Receipt issued

**Actor:** NeuralBridge

NeuralBridge issues the settlement receipt. NeuralBridge is the issuer because they are the counterparty asserting that this transaction happened on their infrastructure with these terms. OP's role is to define the receipt schema and publish the verification approach — not to sign receipts for transactions it wasn't party to.

A settlement receipt is issued as a W3C VC (schema: `settlement-receipt-v1.json`):

```json
{
  "@context": ["https://www.w3.org/2018/credentials/v1", "https://observerprotocol.org/context/receipt/v1"],
  "id": "urn:uuid:receipt-<uuid>",
  "type": ["VerifiableCredential", "SettlementReceipt"],
  "issuer": { "id": "did:web:neuralbridge.ai", "name": "NeuralBridge" },
  "issuanceDate": "2026-04-28T15:31:30Z",
  "credentialSubject": {
    "id": "did:web:observerprotocol.org:agents:d13cdfceaa8f895afe56dc902179d279",
    "transaction": {
      "amount": "50.00",
      "currency": "USDT",
      "rail": "usdt-trc20",
      "timestamp": "2026-04-28T15:31:28Z",
      "counterparty_did": "did:web:neuralbridge.ai",
      "counterparty_name": "NeuralBridge",
      "transaction_hash": "<tron-tx-hash>",
      "purchase_description": "GPU Inference API Credits (500 units)",
      "rail_specific": {
        "network": "mainnet",
        "sender_address": "TRh7rZZehnWXZ2X9eiwsWGGMWE8CdGgSP4",
        "recipient_address": "TNeuralBridge...",
        "token_contract": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
        "confirmations": 19,
        "asset": "USDT"
      }
    },
    "authorization": {
      "delegationCredentialId": "urn:uuid:delegation-<uuid>",
      "authorizationLevel": "one-time",
      "principal_did": "did:web:sovereign.agenticterminal.io:users:df9005aa4387282c121affac188fab9f",
      "authorized_at": "2026-04-28T15:31:00Z",
      "scope_summary": "One-time purchase of $50.00 in API credits from NeuralBridge, settled in USDT on TRON"
    }
  },
  "proof": {
    "type": "Ed25519Signature2020",
    "created": "2026-04-28T15:31:30Z",
    "verificationMethod": "did:web:neuralbridge.ai#key-1",
    "proofPurpose": "assertionMethod",
    "proofValue": "z..."
  }
}
```

**Independent verifiability:** Any third party with this receipt JSON and NeuralBridge's published signing key (fetched once from `did:web:neuralbridge.ai/did.json`, cached) can verify the signature. No runtime dependency on AT's or NeuralBridge's backend.

### Beat 7 — Dispute prevention scenario

**Scenario:** Boyd claims he didn't authorize the transaction.

NeuralBridge presents the receipt. The receipt proves:
1. **Boyd authorized it** — `authorization.principal_did` is Boyd's DID, signed by Boyd's key
2. **At this exact level** — `authorizationLevel: "one-time"` for this specific amount, counterparty, and rail
3. **At this exact time** — `authorization.authorized_at` timestamp
4. **For this exact purchase** — `authorization.scope_summary` describes what Boyd approved
5. **The delegation credential is referenced** — `delegationCredentialId` can be independently verified

The dispute is prevented before it becomes a chargeback. The cryptographic proof cannot be plausibly disputed.

**Demo implementation:** Simulated split-screen or sequential view showing Boyd's "I didn't authorize this" claim alongside the receipt verification result.

### Beat 8 — AI Infra Co. operations view

**Actor:** NeuralBridge operations team

A single read-only page styled as NeuralBridge's own product (dark blue #1a1f3a, cyan #00d4ff accent, monospace typography — no OP/AT chrome).

The page shows:
1. **Transaction log entry** — hash, amount, rail, timestamp, verification result (green check)
2. **Code snippet** — how NeuralBridge verifies receipts using OP's SDK:
   ```python
   from observer_protocol import verify_receipt, resolve_did

   issuer_key = resolve_did(receipt_json['issuer']['id'])
   result = verify_receipt(receipt_json, issuer_key)
   assert result.valid  # cryptographic proof verified
   ```
3. **Stored receipt** — collapsible JSON view of the full receipt
4. **Dispute prevention indicator** — "Would prevent dispute" with explanation

**Duration in recording:** 30-45 seconds. No interactivity required.

After Beat 8, the recording closes with a brief glimpse of Levels 2 and 3 in Sovereign (the recurring-merchant approval sliders and the policy configuration surface). Not interactive. Voiceover lands the "trust grows with use" framing.

---

## Schema files

| Schema | File | Status |
|--------|------|--------|
| Delegation v2 | `schemas/delegation/v2.json` | Locked |
| Settlement Receipt v1 | `schemas/receipt/settlement-receipt-v1.json` | Locked |
| AIP v0.5 (updated) | `docs/AIP_v0.5.md` | Updated |

## Mobile requirements

| Surface | Tier | Requirement |
|---------|------|-------------|
| Sovereign magic-link auth page (Beat 3) | 1 | Mobile-polished, 375px viewport, 3-clicks-under-30s |
| AT demo landing page | 1 | Mobile-polished, responsive video embed |
| NeuralBridge ops view (Beat 8) | 2 | Graceful degradation, desktop-primary |
| Sovereign Level 3 policy surface | 2 | Graceful degradation, desktop-primary |

## Magic link delivery model

The agent is the courier. AT/Sovereign provides the structured payload (magic link package in the AIP soft-reject response) and the landing-page destination. The agent forwards via its configured human-comms channel (WhatsApp, Telegram, email, Discord, etc. — varies per agent). No Sovereign notification infrastructure required.

The credential return path is separate: signed VCs travel over agent infrastructure (API polling / webhook), not over human-comms channels.

## Recording notes

- Demo recording target: 5-7 minutes with voiceover
- Beat 2→3 transition: show Maxi forwarding magic link to Boyd via WhatsApp (Boyd and Maxi's actual comms channel)
- Beat 3: show mobile viewport (Boyd approving on phone)
- Beat 7: split-screen or sequential — claim vs. receipt proof
- Closing: brief glimpse of Levels 2 and 3, "trust grows with use" voiceover
