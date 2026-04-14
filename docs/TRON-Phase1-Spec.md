# Observer Protocol × TRON — Phase 1 Technical Specification

**TRON Rail Integration + Counterparty Receipt Architecture**

---

## Executive Summary

Phase 1 establishes TRON as a fully-supported payment rail within the Observer Protocol ecosystem, enabling agent-to-agent USDT transactions on the TRON blockchain with cryptographically-verifiable reputation tracking.

### Core Innovation: Counterparty-Signed Receipts

Raw blockchain data is insufficient for agent trust scoring. Phase 1 implements **counterparty-signed receipts** — Verifiable Credentials issued by the transacting agent that:
- Anchor to on-chain events (tx_hash)
- Contain both agents' DIDs
- Are cryptographically signed (Ed25519)
- Attach to VACs for trust score computation

---

## 1. TRON Rail Registration

### 1.1 Address Support
- **Algorithm:** secp256k1 (same as Bitcoin/Ethereum)
- **Encoding:** Base58Check with 'T' prefix
- **Format:** 34 characters, e.g., `TJRjDeYXm HL9P5C jUqjAZT9m TcQy7P2r S`

### 1.2 AIP Type Registry Entries

```yaml
rail_types:
  - id: tron
    name: TRON
    description: Native TRX transfers
    icon: 🔴
    
  - id: tron:trc20
    name: TRC-20
    description: USDT and other tokens on TRON
    icon: 💎
    parent: tron
```

### 1.3 TronGrid Integration
- **Endpoint:** `https://api.shasta.trongrid.io` (testnet)
- **Mainnet:** `https://api.trongrid.io` (Phase 3)
- **Verification:** Confirm transaction exists and matches Receipt VC

---

## 2. Transaction Receipt VC Schema

### 2.1 Verifiable Credential Structure

```json
{
  "@context": [
    "https://www.w3.org/2018/credentials/v1",
    "https://observerprotocol.org/contexts/tron-receipt-v1"
  ],
  "type": ["VerifiableCredential", "TronTransactionReceipt"],
  "id": "urn:uuid:receipt-xxx",
  "issuer": "did:web:agent-a.example.com",
  "issuanceDate": "2026-04-13T10:00:00Z",
  "credentialSubject": {
    "id": "did:web:agent-b.example.com",
    "rail": "tron:trc20",
    "asset": "USDT",
    "amount": "100.00",
    "tronTxHash": "0x...",
    "timestamp": 1713002400,
    "orgAffiliation": "Acme Corp"
  },
  "proof": {
    "type": "Ed25519Signature2020",
    "created": "2026-04-13T10:00:00Z",
    "proofPurpose": "assertionMethod",
    "verificationMethod": "did:web:agent-a.example.com#key-1",
    "proofValue": "z58D..."
  }
}
```

### 2.2 Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `issuer` | DID | Agent A (transaction sender) |
| `credentialSubject.id` | DID | Agent B (transaction recipient) |
| `rail` | string | `tron` or `tron:trc20` |
| `asset` | string | `USDT` for TRC-20, `TRX` for native |
| `amount` | string | Decimal amount |
| `tronTxHash` | hex | On-chain transaction reference |
| `timestamp` | epoch | Unix timestamp |
| `orgAffiliation` | string | Optional issuer org from VAC |

---

## 3. VAC Extensions Layer

### 3.1 Extension Type: `tron_receipt_v1`

```json
{
  "type": "tron_receipt_v1",
  "receipts": [
    {
      "vcId": "urn:uuid:receipt-xxx",
      "issuer": "did:web:agent-a.example.com",
      "txHash": "0x...",
      "amount": "100.00",
      "asset": "USDT",
      "timestamp": 1713002400,
      "verified": true
    }
  ]
}
```

### 3.2 Database Schema

```sql
CREATE TABLE tron_receipts (
  id VARCHAR(64) PRIMARY KEY,
  agent_id VARCHAR(255) NOT NULL,
  issuer_did VARCHAR(255) NOT NULL,
  tron_tx_hash VARCHAR(66) NOT NULL,
  rail VARCHAR(20) CHECK (rail IN ('tron', 'tron:trc20')),
  asset VARCHAR(20),
  amount DECIMAL(20, 8),
  timestamp BIGINT,
  vc_data JSONB,
  verified BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. AIP Flow for TRON Transactions

### 4.1 Transaction Flow

```
Step 1: Agent A initiates TRON USDT transfer to Agent B
        ↓
Step 2: TRON network confirms transaction
        ↓
Step 3: Agent A constructs Receipt VC
        - Populate issuer_did (Agent A)
        - Populate subject_did (Agent B)
        - Add tron_tx_hash from network
        - Sign with Ed25519
        ↓
Step 4: Agent A transmits receipt to Agent B via AIP
        POST /aip/v1/receipts
        ↓
Step 5: Agent B submits receipt to OP
        ↓
Step 6: OP verifies
        - Ed25519 signature valid
        - TronGrid confirms tx_hash
        - Receipt attached to Agent B's VAC
        ↓
Step 7: AT trust score recomputed
```

### 4.2 AIP Endpoints

```
POST /aip/v1/receipts
Content-Type: application/json
Authorization: Bearer {agent-b-token}

{
  "receipt_vc": { /* full VC */ },
  "counterparty_did": "did:web:agent-a.example.com"
}
```

---

## 5. Trust Score Integration

### 5.1 Score Dimensions (from Receipt VCs)

| Dimension | Calculation | Source |
|-----------|-------------|--------|
| **Transaction Volume** | Sum of `amount` fields | All receipts |
| **Counterparty Diversity** | Count unique `issuer_did` | Receipt issuers |
| **Recency** | Weighted by `timestamp` | Newer = higher weight |
| **A2A Ratio** | Agent issuers / Total issuers | Receipt metadata |
| **Org-Verified Ratio** | Issuers with org attestation / Total | VAC lookup |

### 5.2 Composite Score Formula

```
Score = (Volume × 0.25) + 
        (Diversity × 0.20) + 
        (Recency × 0.20) + 
        (A2A_Ratio × 0.15) + 
        (Org_Verified × 0.20)

Range: 0-1000
```

### 5.3 Real-Time Updates

- **Trigger:** Webhook fires on `receipt.attached` event
- **Frontend:** 58→83 animation pattern
- **Polling:** Removed (webhook-based)

---

## 6. Implementation Status

### 6.1 Complete ✅

| Component | Status | Tests |
|-----------|--------|-------|
| TRON address derivation | ✅ | 3/3 |
| TronGrid client | ✅ | 2/2 |
| Receipt VC schema | ✅ | 4/4 |
| VAC extensions | ✅ | Migration applied |
| Demo provisioning | ✅ | Manual tested |
| Role-based access | ✅ | All roles working |

### 6.2 Pending ⚠️

| Component | Status | Blocker |
|-----------|--------|---------|
| Webhook trigger | Frontend ready, backend pending | Leo to wire receipt→webhook call |
| Trust score 58→83 animation | Ready, waiting on webhook | Same as above |

---

## 7. Testing

### 7.1 Automated Tests

```bash
cd observer-protocol/rails/tron
npm install
node --test test-tron-rail.mjs

# Expected: 19/19 passing
```

### 7.2 Manual Testing

1. **Shasta Testnet Setup**
   - Get test TRX: https://www.trongrid.io/shasta
   - Verify on explorer: https://shasta.tronscan.io

2. **Test Transaction Flow**
   - Send USDT from Agent A to Agent B
   - Check Receipt VC created
   - Verify on VAC
   - Confirm trust score update

---

## 8. Security Considerations

### 8.1 Key Management
- **Receipt Signing:** Ed25519 keys (agent-controlled)
- **TronGrid API Key:** Server-side only, never client-side
- **DID Private Keys:** Never in browser storage

### 8.2 Verification Requirements
- Signature must verify before storing receipt
- TronGrid must confirm tx_hash exists
- Receipt issuer must match transaction sender

---

## 9. Phase 2+ Roadmap

### Phase 2 (Q3 2026)
- Mainnet deployment
- Production-grade key custody
- Multi-signature support
- Cross-rail atomic swaps

### Phase 3 (Q4 2026)
- Wallet-based org membership (E1)
- Mainnet migration
- Performance optimization
- Enterprise SSO integration

---

## Appendix A: Glossary

- **VAC:** Verifiable Agent Credential — agent's identity document
- **Receipt VC:** Transaction receipt as Verifiable Credential
- **AIP:** Agent Interaction Protocol — communication standard
- **OWS:** Open Wallet Standard — wallet compatibility layer
- **Shasta:** TRON testnet

## Appendix B: References

- [TRON Documentation](https://developers.tron.network/)
- [TronGrid API](https://www.trongrid.io/)
- [W3C Verifiable Credentials](https://www.w3.org/TR/vc-data-model/)
- [AIP Specification](AIP_v0_3_1.md)

---

**Version:** 1.0  
**Date:** April 13, 2026  
**Status:** Phase 1 Complete, Ready for Engineering Review
