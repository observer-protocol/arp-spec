# Observer Protocol TRON Rail — Mainnet Ready

Complete TRON rail integration with counterparty-signed receipt architecture. Supports both Shasta testnet and TRON mainnet via environment-based configuration.

**Status:** ✅ Mainnet Cutover Complete  
**Version:** 1.1.0  
**Date:** 2026-04-20

---

## Quick Start

```bash
# Set required environment variables
export TRON_NETWORK=mainnet  # or 'shasta' for testnet
export TRONGRID_API_KEY=your_trongrid_api_key

# Use the TRON rail
import { TronRail } from './rails/tron/index.mjs';

const tron = new TronRail();
console.log(`Connected to ${tron.network}`);
```

---

## Configuration

The TRON rail uses **environment-based network selection**. The rail will refuse to start if `TRON_NETWORK` is not set.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TRON_NETWORK` | ✅ Yes | Network selection: `mainnet` or `shasta` |
| `TRONGRID_API_KEY` | ✅ Yes | API key for mainnet (get at [trongrid.io](https://www.trongrid.io/)) |
| `TRONGRID_SHASTA_API_KEY` | No | Separate API key for Shasta (falls back to `TRONGRID_API_KEY`) |
| `OP_DID` | No | Observer Protocol DID for the instance |
| `OP_SIGNING_KEY` | No | Private key for signing receipts |

### Network Configuration

#### Mainnet
```bash
export TRON_NETWORK=mainnet
export TRONGRID_API_KEY=your_mainnet_api_key
```

**Mainnet Settings:**
- API Endpoint: `https://api.trongrid.io`
- USDT Contract: `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t`
- Min Confirmations: `19`
- TronScan: `https://tronscan.org`

#### Shasta Testnet
```bash
export TRON_NETWORK=shasta
export TRONGRID_API_KEY=your_api_key
```

**Shasta Settings:**
- API Endpoint: `https://api.shasta.trongrid.io`
- USDT Contract: None (use test tokens)
- Min Confirmations: `1`
- TronScan: `https://shasta.tronscan.org`

---

## Installation

```bash
cd /observer-protocol/rails/tron

# Install dependencies (if any)
npm install

# Run tests
TRON_NETWORK=shasta node --test test-tron-rail.mjs
```

---

## Usage

### Basic Usage

```javascript
import { TronRail } from './rails/tron/index.mjs';

// Initialize (loads config from environment)
const tron = new TronRail();

// Check configuration
console.log(tron.getConfigSummary());
// { network: 'mainnet', apiEndpoint: 'https://api.trongrid.io', ... }
```

### Create a Transaction Receipt

```javascript
const receipt = await tron.createReceipt({
  issuer_did: 'did:op:sender-agent',
  subject_did: 'did:op:receiver-agent',
  rail: 'tron:trc20',
  asset: 'USDT',
  amount: '1000000', // 1 USDT (6 decimals)
  tron_tx_hash: 'a1b2c3d4...', // 64-char hex
  timestamp: '2026-04-20T14:00:00Z',
  sender_address: 'TExEspsjqwjZeqT5BCZPDUvAcRSvgBQdak',
  recipient_address: 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t',
  token_contract: 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'
});

console.log(receipt.id); // urn:uuid:...
```

### Verify a Receipt

```javascript
const result = await tron.verifyReceipt(receipt);

console.log(result.verified);        // true/false
console.log(result.confirmations);   // 19
console.log(result.tronGridVerified); // true
```

### Check Balances

```javascript
// TRX balance (for gas)
const trxBalance = await tron.getTrxBalance('TExEspsjqwjZeqT5BCZPDUvAcRSvgBQdak');
console.log(`TRX: ${trxBalance / 1000000n}`);

// USDT balance
const usdtBalance = await tron.getTRC20Balance('TExEspsjqwjZeqT5BCZPDUvAcRSvgBQdak');
console.log(`USDT: ${usdtBalance / 1000000n}`);

// Check gas sufficiency
const gasCheck = await tron.checkGasBalance('TExEspsjqwjZeqT5BCZPDUvAcRSvgBQdak');
console.log(`Has gas: ${gasCheck.hasGas}`);
```

---

## Mainnet Validation

The validation script performs end-to-end testing of the TRON rail with real transactions.

### Prerequisites

```bash
# Set environment variables
export TRON_NETWORK=mainnet
export TRONGRID_API_KEY=your_api_key
export SENDER_AGENT_DID=did:op:your-sender-agent
export RECEIVER_AGENT_DID=did:op:your-receiver-agent
export SENDER_ADDRESS=T...your_sender_address
export RECEIVER_ADDRESS=T...your_receiver_address

# Optional: Use existing transaction
export TX_HASH=your_existing_tx_hash
```

### Run Validation

```bash
cd /observer-protocol/rails/tron

# Shasta testnet (auto-executes)
TRON_NETWORK=shasta node scripts/validate_mainnet.mjs

# Mainnet (requires confirmation)
TRON_NETWORK=mainnet node scripts/validate_mainnet.mjs
```

**Mainnet execution requires manual confirmation:**
- Script will display transaction details
- Type `yes` to proceed with live transaction
- Type anything else to cancel

### Validation Artifacts

Artifacts are written to `validation/runs/{timestamp}/`:

- **`validation.json`** — Machine-readable results
- **`validation.md`** — Human-readable BD-ready report

### Validation Report Contents

| Section | Description |
|---------|-------------|
| Configuration | Network settings, API endpoint, contract addresses |
| Participants | Sender/receiver DIDs and addresses |
| Balances | Pre-validation wallet balances |
| Transaction | TX hash, TronScan URL, confirmations |
| Receipt VC | Generated Verifiable Credential |
| Submission | OP endpoint response, VAC ID |
| Trust Score | Before/after scores with delta |
| Acceptance | Pass/fail for each criterion |

---

## Error Handling

### Configuration Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `TRON_NETWORK is not set` | Environment variable missing | `export TRON_NETWORK=mainnet` |
| `Invalid TRON_NETWORK` | Wrong value | Use `mainnet` or `shasta` |
| `API key not found` | Missing API key | `export TRONGRID_API_KEY=...` |

### Validation Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Insufficient TRX for gas` | Low TRX balance | Fund wallet with TRX |
| `Insufficient USDT` | Low USDT balance | Fund wallet with USDT |
| `Mainnet contract cannot be used on shasta` | Contract mismatch | Use correct contract for network |
| `Transaction cancelled` | User rejected mainnet tx | Re-run and confirm with `yes` |

---

## File Structure

```
/observer-protocol/rails/tron/
├── index.mjs                 # Main TronRail class
├── tron-config.mjs           # Environment-based configuration
├── tron-core.mjs             # Address derivation, TronGrid client
├── tron-receipt-vc.mjs       # Receipt VC schema, signing
├── tron-verification.mjs     # Verification flow, endpoints
├── test-tron-rail.mjs        # Comprehensive test suite
├── README.md                 # This file
├── INTEGRATION-GUIDE.md      # Detailed integration docs
├── scripts/
│   └── validate_mainnet.mjs  # Mainnet validation script
└── validation/
    └── runs/                 # Validation artifacts
        └── {timestamp}/
            ├── validation.json
            └── validation.md
```

---

## API Reference

### TronRail Class

#### Constructor

```javascript
new TronRail(options)
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `config` | `TronConfig` | from env | Pre-loaded config object |
| `opDid` | `string` | `env.OP_DID` | OP instance DID |
| `signingKey` | `string` | `env.OP_SIGNING_KEY` | Signing private key |
| `timeout` | `number` | 30000 | API timeout (ms) |
| `minConfirmations` | `number` | network default | Required confirmations |

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `getConfigSummary()` | `object` | Config details (API key masked) |
| `isMainnet()` | `boolean` | True if on mainnet |
| `isTestnet()` | `boolean` | True if on shasta/nile |
| `createReceipt(data)` | `Promise<VC>` | Create receipt VC |
| `signReceipt(receipt)` | `Promise<VC>` | Sign receipt |
| `verifyReceipt(receipt)` | `Promise<Result>` | Verify against TronGrid |
| `getTrxBalance(address)` | `Promise<BigInt>` | Get TRX balance |
| `getTRC20Balance(address, contract?)` | `Promise<BigInt>` | Get token balance |
| `checkGasBalance(address)` | `Promise<GasCheck>` | Check gas sufficiency |
| `getUsdtContract()` | `string\|null` | USDT contract address |
| `getTronscanUrl(txHash)` | `string` | TronScan link for TX |
| `getMinConfirmations()` | `number` | Required confirmations |

---

## Phase 1 Components

### ✅ 1. TRON Rail Registration
- Address derivation (secp256k1 → Keccak256 → Base58Check)
- TronGrid API integration with timeout and error handling
- TRC-20 transaction verification (USDT, USDC, TUSD, USDD)
- Mainnet, Shasta, and Nile network support
- AIP Type Registry: `tron`, `tron:trc20`, `tron:native`

### ✅ 2. Transaction Receipt VC Schema
- W3C-compliant `tron_receipt_v1` Verifiable Credential
- Ed25519Signature2020 signing utilities
- Required fields: issuer_did, subject_did, rail, asset, amount, tron_tx_hash, timestamp
- Optional fields: org_affiliation, sender_address, recipient_address, token_contract, confirmations, network

### ✅ 3. VAC Extensions Layer
- Database schema for `tron_receipts` table
- Trust score calculation from TRON receipts
- Receipt attachment to agent VACs

### ✅ 4. AIP Receipt Endpoint
- `/api/v1/tron/receipts/submit` — Submit receipt
- `/api/v1/tron/receipts/{agent_id}` — Get receipts
- `/api/v1/tron/receipts/detail/{receipt_id}` — Get details
- `/api/v1/tron/webhook/trongrid` — Webhook handler

### ✅ 5. OP Verification Flow
- Receipt structure validation
- TronGrid transaction verification
- Confirmation count checking
- Signature verification (when proof present)
- VAC attachment on successful verification

### ✅ 6. AT Trust Score Integration
- Trust score components: Volume, Diversity, Recency, A2A Ratio, Org Verified
- Leaderboard generation
- Score calculation from TRON receipts

### ✅ 7. Mainnet Cutover (NEW)
- Environment-based network selection (`TRON_NETWORK`)
- Separate API keys per network
- Contract validation (mainnet contract on mainnet only)
- Mainnet validation script with confirmation flow
- BD-ready validation reports

---

## Compliance & Security

- **W3C Standards:** VC/VP conform to W3C specifications
- **Ed25519 Signatures:** Industry-standard cryptographic proofs
- **Input Validation:** Pydantic models validate all inputs
- **SQL Injection Protection:** Parameterized queries throughout
- **API Key Security:** Keys masked in logs and summaries
- **Mainnet Protection:** Manual confirmation required for mainnet transactions

---

## Troubleshooting

### "TRON_NETWORK is not set"

```bash
# Set the environment variable
export TRON_NETWORK=mainnet  # or shasta

# Verify it's set
echo $TRON_NETWORK
```

### "API key not found"

```bash
# Get a free API key at https://www.trongrid.io/
export TRONGRID_API_KEY=your_api_key_here

# For separate testnet key:
export TRONGRID_SHASTA_API_KEY=your_shasta_key
```

### "Insufficient TRX for gas"

Fund your wallet with TRX:
- Mainnet: Purchase TRX on an exchange and withdraw to your address
- Shasta: Request test TRX from the [Shasta faucet](https://www.trongrid.io/faucet)

### "Insufficient USDT"

- Mainnet: Purchase USDT and withdraw to your TRON address
- Shasta: USDT is not natively available; use test tokens or native TRX

---

## Testing

### Unit Tests

```bash
cd /observer-protocol/rails/tron

# Run all tests
TRON_NETWORK=shasta node --test test-tron-rail.mjs

# Run with coverage (Node 20+)
TRON_NETWORK=shasta node --test --experimental-test-coverage test-tron-rail.mjs
```

### Integration Test

```bash
# Shasta testnet
TRON_NETWORK=shasta \
  TRONGRID_API_KEY=test_key \
  SENDER_AGENT_DID=did:op:test-sender \
  RECEIVER_AGENT_DID=did:op:test-receiver \
  SENDER_ADDRESS=T... \
  RECEIVER_ADDRESS=T... \
  node scripts/validate_mainnet.mjs
```

---

## License

MIT License — Observer Protocol

---

## Support

- **Documentation:** `/observer-protocol/rails/tron/INTEGRATION-GUIDE.md`
- **Issues:** Create an issue in the repository
- **TronGrid Docs:** https://developers.tron.network/

---

*Implementation by: AI Agent (Kimi K2.5)*  
*Mainnet Cutover: 2026-04-20*

## Production Status

**Mainnet Validated:** 2026-04-20  
**Transaction Hash:** eb52108c9785a83d5ff381d6d5086dec4745d80dbaa1435b816c0f358754a006  
**Tronscan:** https://tronscan.org/#/transaction/eb52108c9785a83d5ff381d6d5086dec4745d80dbaa1435b816c0f358754a006  
**Amount:** 1.00 USDT-TRC20  
**Status:** Phase 2 M4 Complete ✅

The TRON rail has been validated on mainnet with real USDT transfers and end-to-end W3C DID/VC identity attestation.
