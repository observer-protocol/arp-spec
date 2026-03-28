-- Observer Protocol Database Migration - Build 2: MoonPay KYB Integration
-- Run this migration to add Trusted KYB Provider Registry and KYB fields to organizations

-- ============================================================================
-- Build 2a: Trusted KYB Provider Registry
-- ============================================================================

CREATE TABLE IF NOT EXISTS trusted_kyb_providers (
    provider_id VARCHAR(32) PRIMARY KEY,
    provider_name VARCHAR(128) NOT NULL,
    provider_domain VARCHAR(128) NOT NULL,
    provider_public_key_hash VARCHAR(64) NOT NULL,
    api_endpoint VARCHAR(256) NOT NULL,
    status VARCHAR(16) DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    notes TEXT
);

-- ============================================================================
-- Build 1: Organization Registry (if not exists)
-- ============================================================================

CREATE TABLE IF NOT EXISTS organizations (
    id SERIAL PRIMARY KEY,
    org_id VARCHAR(32) UNIQUE NOT NULL,
    org_name VARCHAR(128) NOT NULL,
    domain VARCHAR(128) NOT NULL,
    public_key VARCHAR(128) NOT NULL,
    
    -- Build 2b: KYB fields
    kyb_status VARCHAR(16) DEFAULT 'pending' CHECK (kyb_status IN ('pending', 'verified', 'rejected', 'expired')),
    kyb_provider_id VARCHAR(32) REFERENCES trusted_kyb_providers(provider_id),
    kyb_reference VARCHAR(128),
    kyb_verified_at TIMESTAMP WITH TIME ZONE,
    kyb_expires_at TIMESTAMP WITH TIME ZONE,
    kyb_last_checked_at TIMESTAMP WITH TIME ZONE,
    kyb_response_data JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for organizations
CREATE INDEX IF NOT EXISTS idx_organizations_org_id ON organizations(org_id);
CREATE INDEX IF NOT EXISTS idx_organizations_domain ON organizations(domain);
CREATE INDEX IF NOT EXISTS idx_organizations_kyb_status ON organizations(kyb_status);

-- ============================================================================
-- Update Agent Keys table with org_id reference
-- ============================================================================

ALTER TABLE agent_keys 
ADD COLUMN IF NOT EXISTS org_id VARCHAR(32) REFERENCES organizations(org_id);

CREATE INDEX IF NOT EXISTS idx_agent_keys_org_id ON agent_keys(org_id);

-- ============================================================================
-- Seed MoonPay as the founding Trusted KYB Provider
-- ============================================================================

INSERT INTO trusted_kyb_providers (
    provider_id, 
    provider_name, 
    provider_domain, 
    provider_public_key_hash, 
    api_endpoint, 
    status, 
    notes
) VALUES (
    'provider_001',
    'MoonPay',
    'moonpay.com',
    '0xMOONPAY_PUBLIC_KEY_HASH_PLACEHOLDER',
    'https://mock.moonpay.com/kyb/verify',
    'active',
    'Founding Trusted KYB Provider - Global leader in Web3 payment infrastructure'
)
ON CONFLICT (provider_id) DO UPDATE SET
    provider_name = EXCLUDED.provider_name,
    provider_domain = EXCLUDED.provider_domain,
    api_endpoint = EXCLUDED.api_endpoint,
    status = EXCLUDED.status,
    notes = EXCLUDED.notes;

-- ============================================================================
-- Verify migration
-- ============================================================================

SELECT 'trusted_kyb_providers table created' AS status;
SELECT 'organizations table created/updated' AS status;
SELECT 'agent_keys table updated with org_id' AS status;
SELECT 'MoonPay seeded as provider_001' AS status;
