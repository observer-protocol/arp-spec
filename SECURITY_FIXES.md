# Observer Protocol Security Fixes

**Date:** 2026-03-26
**Status:** ✅ COMPLETED

## Summary

Three critical security vulnerabilities have been identified and fixed in the Observer Protocol backend:

1. **Public keys stored in-memory only** - Keys reset on server restart, causing reliability issues
2. **Incomplete `recover_public_key_from_signature()` function** - Function was a stub returning placeholder
3. **Missing transaction signature verification** - `submit-transaction` endpoint accepted unsigned transactions

---

## PRIORITY 1: Persist Public Keys to Database ✅

### Problem
Public keys were stored only in the `_PUBLIC_KEY_CACHE` dictionary in memory. On server restart, all cached keys were lost, causing verification failures for registered agents.

### Solution

#### 1. Created Database Migration
**File:** `migrations/001_add_public_keys_table.py`

Creates a new `public_keys` table with the following schema:
- `id` - SERIAL PRIMARY KEY
- `pubkey` - TEXT NOT NULL (the actual public key)
- `pubkey_hash` - TEXT UNIQUE NOT NULL (SHA256 hash for lookups)
- `agent_id` - TEXT (optional, for agent association)
- `created_at` - TIMESTAMP WITH TIME ZONE
- `verified` - BOOLEAN DEFAULT FALSE

Indexes created on:
- `pubkey` (for efficient lookup)
- `pubkey_hash` (unique constraint enforcement)
- `agent_id` (for agent lookups)

#### 2. Added Database Persistence Functions
**File:** `crypto_verification.py`

New functions:
- `persist_public_key(agent_id, public_key_hex, verified)` - Save key to DB and cache
- `load_public_key_from_db(agent_id)` - Load key from DB
- `load_all_public_keys_from_db()` - Load all keys on startup
- `get_public_key(agent_id)` - Get key (cache first, then DB)
- `verify_public_key_signature(message, signature_hex, agent_id)` - Verify using stored key

#### 3. Updated Registration Flow
**File:** `api-server-v2.py`

- `register_agent()` now calls `persist_public_key()` to save keys to database
- `startup_event()` loads all keys from DB on server startup

### Run Migration
```bash
cd /home/futurebit/.openclaw/workspace/observer-protocol-repo
python migrations/001_add_public_keys_table.py
```

### Rollback (if needed)
```bash
python migrations/001_add_public_keys_table.py --rollback
```

---

## PRIORITY 2: Fix `recover_public_key_from_signature()` ✅

### Problem
The function was an incomplete stub that returned a placeholder string (`"recovery_requires_full_implementation"`) instead of actually recovering the public key.

### Solution
**File:** `crypto_verification.py`

Implemented proper public key recovery using:

#### Option A: coincurve library (recommended)
Uses the `coincurve` library for proper secp256k1 public key recovery:
- Tries all 4 recovery IDs (0-3)
- Returns compressed public key (33 bytes)
- Most reliable implementation

#### Option B: cryptography library fallback
Manual elliptic curve point operations for recovery:
- Implements recovery algorithm using curve parameters
- Falls back when coincurve is not available

### Function Signature
```python
def recover_public_key_from_signature(message: bytes, signature_hex: str) -> tuple:
    """
    Returns: (public_key_hex, recovery_id) or (None, None) if failed
    """
```

### Dependencies
```bash
pip install coincurve  # Optional but recommended for reliable recovery
```

---

## PRIORITY 3: Add Transaction Signature Verification ✅

### Problem
The `submit-transaction` endpoint accepted transaction data without verifying cryptographic signatures. This allowed anyone to submit transactions on behalf of any agent.

### Solution
**File:** `api-server-v2.py`

#### Updated `submit_transaction()` Endpoint

**Request Parameters (same as before):**
- `agent_id` - Agent's unique ID
- `protocol` - Payment protocol (e.g., "L402")
- `transaction_reference` - Transaction hash/reference
- `timestamp` - ISO8601 timestamp
- `signature` - **REQUIRED** - Cryptographic signature
- `optional_metadata` - JSON string with additional data

**Error Handling:**
- Missing signature → `400 Bad Request`
- Invalid signature → `401 Unauthorized`
- Correct signature → Transaction accepted

**Message Format for Signing:**
```json
{
  "agent_id": "<agent_id>",
  "protocol": "<protocol>",
  "transaction_reference": "<tx_ref>",
  "timestamp": "<timestamp>",
  "amount_sats": <amount>,  // from metadata
  "counterparty_id": "<id>",  // from metadata
  "event_type": "<type>",  // from metadata
  "direction": "<direction>"  // from metadata
}
```

Canonical JSON format (sorted keys, no spaces) is used for consistent signing.

### API Changes

**Before:**
```bash
curl -X POST "https://api.agenticterminal.ai/observer/submit-transaction" \
  -d "agent_id=abc123" \
  -d "protocol=L402" \
  -d "transaction_reference=tx_hash" \
  -d "timestamp=2024-01-01T00:00:00Z" \
  -d "signature=optional_not_verified"
```

**After:**
```bash
# 1. Create message
MESSAGE='{"agent_id":"abc123","protocol":"L402","transaction_reference":"tx_hash","timestamp":"2024-01-01T00:00:00Z"}'

# 2. Sign with private key (client-side)
SIGNATURE=$(echo -n "$MESSAGE" | sign_with_private_key)

# 3. Submit with signature
curl -X POST "https://api.agenticterminal.ai/observer/submit-transaction" \
  -d "agent_id=abc123" \
  -d "protocol=L402" \
  -d "transaction_reference=tx_hash" \
  -d "timestamp=2024-01-01T00:00:00Z" \
  -d "signature=$SIGNATURE"
```

---

## Test Coverage

### New Test File: `test_security_fixes.py`

Comprehensive test suite covering all three fixes:

```bash
python test_security_fixes.py
```

**Test Results:**
```
✅ All 13 tests passed

Test Categories:
- TestPublicKeyPersistence (4 tests)
- TestPublicKeyRecovery (4 tests)
- TestTransactionSignatureVerification (4 tests)
- TestIntegration (1 test)
```

---

## Files Modified

| File | Changes |
|------|---------|
| `migrations/001_add_public_keys_table.py` | **NEW** - Database migration for public_keys table |
| `crypto_verification.py` | **MODIFIED** - Fixed recovery function, added DB persistence |
| `api-server-v2.py` | **MODIFIED** - Added signature verification, startup loading |
| `test_security_fixes.py` | **NEW** - Comprehensive test suite |

---

## Deployment Checklist

- [x] Create database migration script
- [x] Run migration to create public_keys table
- [x] Update crypto_verification.py with persistence functions
- [x] Fix recover_public_key_from_signature() implementation
- [x] Update api-server-v2.py with signature verification
- [x] Add startup event to load keys from database
- [x] Create comprehensive test suite
- [x] Run all tests (all passing)
- [ ] Restart API server (manual step)

---

## Backward Compatibility

### Breaking Changes
- `submit-transaction` endpoint now **requires** a valid signature
- Clients that were not signing transactions will receive `401 Unauthorized`

### Migration Path for Clients
1. Register agent (if not already registered)
2. Sign transaction data using agent's private key
3. Include signature in submit-transaction request

### Non-Breaking Changes
- Public key persistence is additive - existing agents continue to work
- Database migration is idempotent (can be run multiple times safely)

---

## Security Impact

| Vulnerability | Before | After | Risk Level |
|--------------|--------|-------|------------|
| In-memory key storage | Keys lost on restart | Keys persisted to DB | ✅ Fixed |
| Unimplemented recovery | Placeholder function | Full implementation | ✅ Fixed |
| Unsigned transactions | Accepted without verification | Require valid signature | ✅ Fixed |

---

## Next Steps

1. **Deploy to production:**
   ```bash
   # Run migration
   python migrations/001_add_public_keys_table.py
   
   # Restart API server
   sudo systemctl restart observer-protocol-api
   ```

2. **Update client SDKs:** Document new signature requirement

3. **Monitor logs:** Watch for 401 errors from clients that need updating

4. **Install coincurve (optional but recommended):**
   ```bash
   pip install coincurve
   ```

---

## Questions?

Contact: Boyd / ArcadiaB Team
