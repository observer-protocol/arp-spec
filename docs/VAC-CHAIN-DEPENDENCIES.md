# VAC Chain Dependencies

## Issue: Missing Bridge from `tron_receipts` to `verified_events`

### Summary

The VAC (Verifiable Agent Credential) generator queries the `verified_events` table to compute trust scores and transaction history. However, the bridge from `tron_receipts` → `agent_transactions` (implemented in Spec 2.5) does not extend to populate `verified_events`, creating a downstream gap.

### Affected Components

1. **VAC Generator** (`vac/generator.py` or similar)
   - Queries `verified_events` table for agent transaction history
   - Uses this data to compute `total_transactions`, `total_volume_sats`, and trust scores

2. **TRON Receipt Pipeline** (`rails/tron/`)
   - Successfully persists receipts to `tron_receipts` table
   - Bridge to `agent_transactions` exists and fires correctly
   - Does NOT populate `verified_events` table

3. **Trust Score Calculation**
   - Depends on `verified_events` for complete transaction history
   - Missing TRON transactions in `verified_events` leads to incomplete trust scores

### Current Data Flow

```
TRON Transaction
       ↓
[tron_receipts] ←── Receipt VC submitted
       ↓
[agent_transactions] ←── Bridge fires (Spec 2.5)
       ↗
[verified_events] ←── GAP: Not populated from tron_receipts
       ↓
VAC Generator queries verified_events
       ↓
VAC with incomplete transaction history
```

### Expected Data Flow

```
TRON Transaction
       ↓
[tron_receipts] ←── Receipt VC submitted
       ↓
[agent_transactions] ←── Bridge fires
       ↓
[verified_events] ←── SHOULD be populated from tron_receipts
       ↓
VAC Generator queries verified_events
       ↓
VAC with complete transaction history
```

### Technical Details

#### `tron_receipts` Table Schema
- `receipt_id` (UUID)
- `vc_id` (string)
- `issuer_did` (string)
- `subject_did` (string)
- `subject_agent_id` (string)
- `rail` (string)
- `asset` (string)
- `amount` (string)
- `tron_tx_hash` (string, 64 hex chars)
- `sender_address` (string)
- `recipient_address` (string)
- `token_contract` (string)
- `network` (string)
- `tx_timestamp` (timestamp)
- `confirmations` (integer)
- `verified` (boolean)
- `issued_at` (timestamp)
- `vc_document` (JSON)

#### `verified_events` Table Schema (for reference)
- Event records from various sources (lightning, tron, etc.)
- Used by VAC generator for trust score computation
- Currently populated by lightning transactions and other sources

### Options for Resolution

#### Option 1: Extend the Bridge (Recommended for Spec 2.5+)
Add logic to the existing bridge from `tron_receipts` → `agent_transactions` to also insert into `verified_events`.

**Pros:**
- Minimal changes to existing architecture
- Consistent with current bridge pattern

**Cons:**
- `verified_events` schema may need updates to accommodate TRON-specific fields

#### Option 2: Update VAC Generator to Query `tron_receipts`
Modify the VAC generator to directly query `tron_receipts` in addition to `verified_events`.

**Pros:**
- No new bridge needed
- Direct access to TRON-specific data

**Cons:**
- VAC generator becomes more complex
- Breaks abstraction layer

#### Option 3: Create Unified Transaction View
Create a database view that unions `verified_events` and `tron_receipts` for VAC generator consumption.

**Pros:**
- Clean abstraction
- No schema changes needed

**Cons:**
- View may have performance implications
- Still requires query changes

### Recommendation

**Implement Option 1** as part of a future Spec 2.6 or Spec 3 update. This maintains architectural consistency and ensures all verified transactions flow through the same pipeline.

### Workaround for Current Demo

For the Spec 2 demo purposes, the bridge to `agent_transactions` is sufficient. The VAC will show:
- `has_vc=true` in `agent_transactions.metadata`
- Trust score calculation may be incomplete until `verified_events` bridge is implemented

### Related Files

- `/media/nvme/observer-protocol/api/api-server-v2.py` - Receipt submission endpoint
- `/media/nvme/observer-protocol/rails/tron/tron-verification.mjs` - Receipt verification
- `/media/nvme/observer-protocol/rails/tron/tron-receipt-vc.mjs` - Receipt VC schema
- VAC generator (location TBD) - Consumes verified_events

### Tracking

- **Status:** Documented, awaiting future spec
- **Priority:** Medium (blocks complete trust score accuracy)
- **Estimated Effort:** 2-4 hours to implement bridge extension
