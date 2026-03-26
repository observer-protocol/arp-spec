# Organization Registry - Implementation Guide
## Observer Protocol - Organizational Attestation Phase 1

**Version:** 1.0.0  
**Status:** Implemented  
**Date:** March 2026  

---

## Overview

The Organization Registry enables enterprises and organizations to cryptographically register as credential issuers in Observer Protocol. This is **Phase 1** of the Organizational Attestation feature, providing the foundational infrastructure for enterprise delegation of authority to autonomous agents.

### Key Design Principles

1. **Organizations are credential issuers, not agents** - They attest to agent claims but don't perform economic activity
2. **Self-attested registration** - OP does NOT verify real-world identity in Phase 1; we only anchor the cryptographic attestation
3. **Separate revocation keypair** - Organizations maintain a distinct keypair for revocation operations (security best practice)
4. **Query by multiple identifiers** - Registry entries can be looked up by `org_id`, `domain`, or `public_key_hash`

---

## Architecture

### Database Schema

The `organizations` table stores organization profiles and cryptographic keys:

```sql
CREATE TABLE organizations (
    org_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    domain VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(200),
    description TEXT,
    master_public_key VARCHAR(500) NOT NULL,
    master_public_key_hash VARCHAR(64) NOT NULL UNIQUE,
    revocation_public_key VARCHAR(500) NOT NULL,
    revocation_public_key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_type VARCHAR(20) NOT NULL CHECK (key_type IN ('secp256k1', 'ed25519')),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    registered_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    revoked_by UUID REFERENCES organizations(org_id),
    revocation_reason TEXT,
    metadata JSONB DEFAULT '{}',
    verification_status VARCHAR(50) NOT NULL DEFAULT 'self_attested',
    contact_email VARCHAR(255),
    verification_documents JSONB DEFAULT '{}'
);
```

### Indexes

- `idx_organizations_domain` - Domain lookups
- `idx_organizations_master_key_hash` - Cryptographic verification
- `idx_organizations_revocation_key_hash` - Revocation key lookups
- `idx_organizations_status` - Status filtering
- `idx_organizations_registered_at` - Recent registrations

---

## API Endpoints

### 1. Register Organization

```http
POST /observer/register-org
```

Register a new organization in the registry.

**Request Body:**
```json
{
  "name": "Acme Corporation",
  "domain": "acme.com",
  "display_name": "Acme Corp",
  "description": "Enterprise software solutions",
  "master_public_key": "04a1b2c3d4e5f6...",
  "revocation_public_key": "04f6e5d4c3b2a1...",
  "key_type": "secp256k1",
  "contact_email": "security@acme.com",
  "metadata": {"industry": "technology", "founded": "2020"}
}
```

**Response (201 Created):**
```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Acme Corporation",
  "domain": "acme.com",
  "master_public_key_hash": "a1b2c3d4e5f6...",
  "revocation_public_key_hash": "f6e5d4c3b2a1...",
  "key_type": "secp256k1",
  "status": "active",
  "verification_status": "self_attested",
  "registered_at": "2026-03-24T10:00:00Z",
  "message": "Organization registered successfully. Note: This is a self-attested registration."
}
```

**Error Responses:**
- `400 Bad Request` - Invalid input (domain format, duplicate keys, etc.)
- `409 Conflict` - Domain or key hash already exists

---

### 2. Get Organization by ID

```http
GET /observer/orgs/{org_id}
```

Retrieve organization details.

**Query Parameters:**
- `include_keys` (boolean, default: false) - Include full public keys in response

**Response (200 OK):**
```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Acme Corporation",
  "domain": "acme.com",
  "display_name": "Acme Corp",
  "description": "Enterprise software solutions",
  "master_public_key_hash": "a1b2c3d4e5f6...",
  "revocation_public_key_hash": "f6e5d4c3b2a1...",
  "key_type": "secp256k1",
  "status": "active",
  "verification_status": "self_attested",
  "registered_at": "2026-03-24T10:00:00Z",
  "updated_at": "2026-03-24T10:00:00Z",
  "metadata": {"industry": "technology"}
}
```

---

### 3. Get Organization by Domain

```http
GET /observer/orgs/by-domain/{domain}
```

Lookup organization by domain (case-insensitive).

**Example:**
```http
GET /observer/orgs/by-domain/acme.com
```

**Response:** Same as Get Organization by ID

---

### 4. Get Organization by Key Hash

```http
GET /observer/orgs/by-key/{key_hash}
```

Lookup organization by SHA256 hash of public key (master or revocation).

**Example:**
```http
GET /observer/orgs/by-key/a1b2c3d4e5f6...
```

**Response:** Same as Get Organization by ID

---

### 5. List Organizations

```http
GET /observer/orgs
```

List organizations with filtering and pagination.

**Query Parameters:**
- `status` (string, default: "active") - Filter by status: active, suspended, revoked, all
- `verification_status` (string) - Filter by verification level
- `domain` (string) - Filter by domain (partial match)
- `limit` (integer, default: 50, max: 100) - Maximum results
- `offset` (integer, default: 0) - Pagination offset

**Response (200 OK):**
```json
{
  "organizations": [...],
  "count": 50,
  "total": 127,
  "limit": 50,
  "offset": 0
}
```

---

### 6. Revoke Organization

```http
POST /observer/orgs/{org_id}/revoke
```

Revoke an organization (soft delete). **Cannot be undone.**

**Request Body:**
```json
{
  "reason": "Key compromise - rotating to new keypair",
  "revocation_signature": "3045022100..."
}
```

**Response (200 OK):**
```json
{
  "org_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Acme Corporation",
  "domain": "acme.com",
  "status": "revoked",
  "revoked_at": "2026-03-24T12:00:00Z",
  "reason": "Key compromise - rotating to new keypair",
  "message": "Organization revoked successfully. All credentials issued by this organization should be considered invalid."
}
```

**Note:** In Phase 1, the `revocation_signature` is optional. Future phases will require cryptographic proof of revocation key ownership.

---

## Key Concepts

### Master vs. Revocation Keys

Organizations maintain **two separate keypairs**:

1. **Master Keypair** - Used for signing attestations and credentials
2. **Revocation Keypair** - Used exclusively for revocation operations

This separation enhances security:
- If master key is compromised, revocation key can revoke the organization
- Revocation key can be stored offline/air-gapped for maximum security
- Clear separation of concerns between signing and revocation operations

### Self-Attested Registration

In Phase 1, organizations self-register without KYB (Know Your Business) verification:

- Anyone can register any domain (we don't verify DNS ownership in Phase 1)
- No document verification required
- `verification_status` is always "self_attested"

**Future phases** will add optional KYB verification:
- `verification_status` can transition to "pending_kyb", "kyb_verified", or "kyb_failed"
- Verified organizations will display a verification badge
- Platforms can choose to only trust KYB-verified organizations

### Status Lifecycle

```
         register
            │
            ▼
    ┌───────────────┐
    │    active     │◄────────────────┐
    └───────┬───────┘                 │
            │                         │
      suspend │ reactivate            │
            ▼                         │
    ┌───────────────┐                 │
    │  suspended    │─────────────────┘
    └───────┬───────┘
            │ revoke
            ▼
    ┌───────────────┐
    │   revoked     │  (permanent)
    └───────────────┘
```

- **Active** - Organization can issue credentials
- **Suspended** - Temporarily deactivated (can be reactivated)
- **Revoked** - Permanently deactivated (cannot be reactivated)

---

## Use Cases

### 1. Enterprise Delegation (Goldman Sachs Example)

Goldman Sachs registers as an organization:

```json
POST /observer/register-org
{
  "name": "Goldman Sachs",
  "domain": "goldmansachs.com",
  "master_public_key": "04...",
  "revocation_public_key": "04...",
  "key_type": "secp256k1"
}
```

Now Goldman Sachs can issue attestations:
- "This agent is authorized to trade on behalf of GS"
- "This agent has passed our compliance review"
- "This agent is operating in jurisdiction X"

Agents include these attestations in their VAC credentials, proving enterprise backing.

### 2. Domain-Based Verification

Platforms can verify that an attestation came from a specific domain:

1. Receive attestation signed by organization's master key
2. Extract public key from signature
3. Compute SHA256 hash
4. Query `GET /observer/orgs/by-key/{hash}`
5. Verify returned domain matches expected domain

### 3. Revocation Checking

Before trusting an organization's attestation:

1. Query `GET /observer/orgs/{org_id}`
2. Verify `status` is "active"
3. If "revoked", reject all credentials from this organization

---

## Security Considerations

### Key Management

Organizations **must**:
- Store master private key securely (HSM, secure enclave, or offline)
- Store revocation private key separately (ideally offline/air-gapped)
- Never share private keys between organizations
- Rotate keys periodically (requires re-registration)

### Domain Verification (Future)

Phase 1 does not verify domain ownership. This means:
- Anyone can register "goldmansachs.com"
- Platforms must treat self-attested registrations with appropriate skepticism
- Future phases will add DNS-based domain verification

### Revocation

Revocation is **permanent and immediate**:
- Revoked organizations cannot be reactivated
- All credentials issued by the organization should be considered invalid
- No grace period or appeal process in Phase 1

---

## Integration Guide

### For Platforms

1. **Query organization status** before trusting attestations:
   ```python
   org = get_organization(attestation.org_id)
   if org['status'] != 'active':
       reject_attestation()
   ```

2. **Verify key ownership** cryptographically:
   ```python
   # Compute hash of attestation signing key
   key_hash = sha256(attestation.public_key).hexdigest()
   
   # Verify it matches organization's master key
   org = get_organization_by_key_hash(key_hash)
   assert org['org_id'] == expected_org_id
   ```

3. **Display verification status** to users:
   - Show "Self-attested" badge for Phase 1 registrations
   - Show "KYB Verified" badge for future verified organizations

### For Organizations

1. **Generate keypairs** using standard tools:
   ```bash
   # secp256k1 (Bitcoin/Ethereum compatible)
   openssl ecparam -genkey -name secp256k1 -out master.key
   openssl ec -in master.key -pubout -out master.pub
   
   # Ed25519 (Solana compatible)
   openssl genpkey -algorithm ed25519 -out revocation.key
   openssl pkey -in revocation.key -pubout -out revocation.pub
   ```

2. **Register** both keys:
   - Extract hex-encoded public keys
   - Call `POST /observer/register-org`
   - Store returned `org_id` for future reference

3. **Issue attestations** by signing claims with master key:
   - Create attestation payload
   - Sign with master private key
   - Include signature in attestation

4. **Monitor status** and be ready to revoke if keys are compromised:
   - Store revocation key securely (offline)
   - If master key is compromised, immediately call `POST /observer/orgs/{org_id}/revoke`

---

## Files Created/Modified

### New Files

1. `/agentic-terminal-db/migrations/006_organization_registry.sql` - Database migration
2. `/observer-protocol-repo/organization_models.py` - Pydantic models
3. `/observer-protocol-repo/organization_registry.py` - Registry module
4. `/observer-protocol-repo/organization_api.py` - FastAPI endpoints (standalone router)
5. `/observer-protocol-repo/test_organization_registry.py` - Comprehensive tests
6. `/observer-protocol-repo/ORGANIZATION-REGISTRY-GUIDE.md` - This documentation

### Modified Files

1. `/observer-protocol-repo/api-server-v2.py` - Added organization endpoints

---

## Testing

Run the test suite:

```bash
cd /home/futurebit/.openclaw/workspace/observer-protocol-repo
pytest test_organization_registry.py -v
```

Run integration tests (requires database):

```bash
pytest test_organization_registry.py -v -m integration
```

Manual testing with curl:

```bash
# Register an organization
curl -X POST http://localhost:8000/observer/register-org \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Corp",
    "domain": "testcorp.example.com",
    "master_public_key": "04a1b2c3d4e5f6789012345678901234567890abcdef",
    "revocation_public_key": "04f6e5d4c3b2a198765432109876543210fedcba",
    "key_type": "secp256k1"
  }'

# Get organization by ID
curl http://localhost:8000/observer/orgs/{org_id}

# List organizations
curl "http://localhost:8000/observer/orgs?limit=10"

# Revoke organization
curl -X POST http://localhost:8000/observer/orgs/{org_id}/revoke \
  -H "Content-Type: application/json" \
  -d '{"reason": "Test revocation"}'
```

---

## Roadmap

### Phase 1 (Current) - ✅ Complete
- Basic organization registry
- Self-attested registration
- Key storage and lookup
- Revocation (soft delete)

### Phase 2 (Planned)
- Cryptographic signature verification for revocation
- Domain ownership verification (DNS challenge)
- Webhook notifications for status changes
- Organization metadata standards

### Phase 3 (Planned)
- KYB (Know Your Business) integration
- Document verification
- Compliance status tracking
- Verified organization badges

### Phase 4 (Planned)
- Hierarchical organizations (subsidiaries)
- Multi-signature requirements
- Organization reputation scoring
- Cross-organization attestation chains

---

## Support

For questions or issues:
- GitHub: github.com/observer-protocol
- API Docs: api.observerprotocol.org/docs
- Email: dev@observerprotocol.org

---

*Observer Protocol - Enabling trust in the agentic economy*
