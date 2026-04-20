-- Migration: TRON Rail Receipt Support
-- Observer Protocol Phase 1: TRON Integration
-- Adds tron_receipt_v1 storage and indexing

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- TRON RECEIPTS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS tron_receipts (
    receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Receipt identification
    receipt_type VARCHAR(50) NOT NULL DEFAULT 'tron_receipt_v1',
    vc_id VARCHAR(200) NOT NULL UNIQUE, -- Verifiable Credential ID
    
    -- Agent references
    issuer_did VARCHAR(500) NOT NULL,
    subject_did VARCHAR(500) NOT NULL,
    subject_agent_id VARCHAR(64) REFERENCES observer_agents(agent_id),
    
    -- Transaction details
    rail VARCHAR(50) NOT NULL CHECK (rail IN ('tron', 'tron:trc20', 'tron:native')),
    asset VARCHAR(50) NOT NULL,
    amount VARCHAR(78) NOT NULL, -- BigInt as string (up to uint256)
    tron_tx_hash VARCHAR(64) NOT NULL,
    sender_address VARCHAR(34),
    recipient_address VARCHAR(34),
    token_contract VARCHAR(34), -- TRC-20 contract address
    
    -- Network and timing
    network VARCHAR(20) DEFAULT 'mainnet' CHECK (network IN ('mainnet', 'shasta', 'nile')),
    tx_timestamp TIMESTAMPTZ NOT NULL,
    confirmations INTEGER DEFAULT 0,
    
    -- Organization affiliation
    org_affiliation VARCHAR(200),
    
    -- Verification status
    verified BOOLEAN DEFAULT FALSE,
    tron_grid_verified BOOLEAN DEFAULT FALSE,
    signature_verified BOOLEAN DEFAULT FALSE,
    verification_error TEXT,
    
    -- Timestamps
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    
    -- Full VC storage (JSONB for flexibility)
    vc_document JSONB NOT NULL,
    
    -- Receipt hash for integrity
    receipt_hash VARCHAR(64) NOT NULL
);

-- Indexes for efficient queries
CREATE INDEX idx_tron_receipts_subject ON tron_receipts(subject_agent_id);
CREATE INDEX idx_tron_receipts_issuer ON tron_receipts(issuer_did);
CREATE INDEX idx_tron_receipts_tx_hash ON tron_receipts(tron_tx_hash);
CREATE INDEX idx_tron_receipts_rail ON tron_receipts(rail);
CREATE INDEX idx_tron_receipts_asset ON tron_receipts(asset);
CREATE INDEX idx_tron_receipts_verified ON tron_receipts(verified) WHERE verified = TRUE;
CREATE INDEX idx_tron_receipts_timestamp ON tron_receipts(tx_timestamp DESC);
CREATE INDEX idx_tron_receipts_expires ON tron_receipts(expires_at) WHERE verified = TRUE;

-- Partial index for org-affiliated receipts
CREATE INDEX idx_tron_receipts_org ON tron_receipts(org_affiliation) WHERE org_affiliation IS NOT NULL;

COMMENT ON TABLE tron_receipts IS 'Stores verified TRON transaction receipts from counterparty agents';
COMMENT ON COLUMN tron_receipts.vc_id IS 'Unique identifier from the Verifiable Credential';
COMMENT ON COLUMN tron_receipts.receipt_hash IS 'SHA256 hash of the canonical credential subject for integrity verification';

-- ============================================================
-- TRON RECEIPT COUNTERPARTY STATS
-- ============================================================

CREATE TABLE IF NOT EXISTS tron_receipt_counterparties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(64) NOT NULL REFERENCES observer_agents(agent_id),
    counterparty_did VARCHAR(500) NOT NULL,
    
    -- Stats
    receipt_count INTEGER DEFAULT 0,
    total_volume_trx NUMERIC(78, 0) DEFAULT 0,
    total_volume_usdt NUMERIC(78, 0) DEFAULT 0,
    first_receipt_at TIMESTAMPTZ,
    last_receipt_at TIMESTAMPTZ,
    
    -- Unique constraint
    UNIQUE(agent_id, counterparty_did)
);

CREATE INDEX idx_tron_counterparties_agent ON tron_receipt_counterparties(agent_id);
CREATE INDEX idx_tron_counterparties_did ON tron_receipt_counterparties(counterparty_did);
CREATE INDEX idx_tron_counterparties_last ON tron_receipt_counterparties(last_receipt_at DESC);

COMMENT ON TABLE tron_receipt_counterparties IS 'Aggregated stats per agent-counterparty pair for trust scoring';

-- ============================================================
-- VAC EXTENSION: TRON RECEIPTS ARRAY
-- ============================================================

-- Add tron_receipts array to vac_credentials
ALTER TABLE vac_credentials 
ADD COLUMN IF NOT EXISTS tron_receipts JSONB DEFAULT '[]'::jsonb;

COMMENT ON COLUMN vac_credentials.tron_receipts IS 'Array of verified TRON receipt summaries attached to VAC';

-- ============================================================
-- AIP TYPE REGISTRY UPDATE
-- ============================================================

-- Insert TRON rail types
INSERT INTO protocols (name, category, description, status, official_url)
VALUES 
    ('tron', 'stablecoin', 'TRON blockchain for USDT and TRC-20 transfers', 'active', 'https://tron.network'),
    ('tron:trc20', 'stablecoin', 'TRON TRC-20 token standard', 'active', 'https://tron.network'),
    ('tron:native', 'stablecoin', 'Native TRX transfers on TRON', 'active', 'https://tron.network')
ON CONFLICT (name) DO UPDATE SET
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    status = EXCLUDED.status;

-- ============================================================
-- TRUST SCORE INTEGRATION VIEWS
-- ============================================================

-- View for AT trust score calculation
CREATE OR REPLACE VIEW v_tron_trust_metrics AS
SELECT 
    subject_agent_id as agent_id,
    COUNT(*) as tron_receipt_count,
    COUNT(DISTINCT issuer_did) as unique_tron_counterparties,
    SUM(CASE 
        WHEN asset = 'TRX' THEN amount::numeric 
        ELSE 0 
    END) as total_trx_volume,
    SUM(CASE 
        WHEN asset IN ('USDT', 'USDC', 'TUSD', 'USDD') THEN amount::numeric 
        ELSE 0 
    END) as total_stablecoin_volume,
    MAX(tx_timestamp) as last_tron_tx,
    COUNT(CASE WHEN org_affiliation IS NOT NULL THEN 1 END) as org_affiliated_count,
    COUNT(CASE WHEN tron_grid_verified THEN 1 END) as verified_count
FROM tron_receipts
WHERE verified = TRUE
  AND expires_at > NOW()
GROUP BY subject_agent_id;

COMMENT ON VIEW v_tron_trust_metrics IS 'Aggregated TRON metrics for AT trust score calculation';

-- ============================================================
-- FUNCTIONS
-- ============================================================

-- Function to attach receipt to VAC
CREATE OR REPLACE FUNCTION attach_tron_receipt_to_vac(
    p_receipt_id UUID,
    p_agent_id VARCHAR
) RETURNS VOID AS $$
DECLARE
    receipt_summary JSONB;
    vac_id UUID;
BEGIN
    -- Get receipt summary
    SELECT jsonb_build_object(
        'type', 'tron_receipt_v1',
        'receiptId', vc_id,
        'issuerDid', issuer_did,
        'rail', rail,
        'asset', asset,
        'amount', amount,
        'tronTxHash', tron_tx_hash,
        'timestamp', tx_timestamp,
        'orgAffiliation', org_affiliation,
        'verified', verified,
        'issuedAt', issued_at,
        'expiresAt', expires_at
    ) INTO receipt_summary
    FROM tron_receipts
    WHERE receipt_id = p_receipt_id;

    IF receipt_summary IS NULL THEN
        RAISE EXCEPTION 'Receipt % not found', p_receipt_id;
    END IF;

    -- Get latest VAC for agent
    SELECT credential_id INTO vac_id
    FROM vac_credentials
    WHERE agent_id = p_agent_id
      AND is_revoked = FALSE
      AND expires_at > NOW()
    ORDER BY issued_at DESC
    LIMIT 1;

    IF vac_id IS NULL THEN
        RAISE EXCEPTION 'No active VAC found for agent %', p_agent_id;
    END IF;

    -- Attach receipt to VAC
    UPDATE vac_credentials
    SET tron_receipts = tron_receipts || jsonb_build_array(receipt_summary)
    WHERE credential_id = vac_id;

END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION attach_tron_receipt_to_vac IS 'Attaches a verified TRON receipt to the agents VAC';

-- Function to update counterparty stats
CREATE OR REPLACE FUNCTION update_tron_counterparty_stats(
    p_receipt_id UUID
) RETURNS VOID AS $$
DECLARE
    r RECORD;
BEGIN
    -- Get receipt details
    SELECT 
        subject_agent_id,
        issuer_did,
        asset,
        amount::numeric,
        tx_timestamp
    INTO r
    FROM tron_receipts
    WHERE receipt_id = p_receipt_id;

    IF r.subject_agent_id IS NULL THEN
        RETURN;
    END IF;

    -- Insert or update counterparty stats
    INSERT INTO tron_receipt_counterparties (
        agent_id,
        counterparty_did,
        receipt_count,
        total_volume_trx,
        total_volume_usdt,
        first_receipt_at,
        last_receipt_at
    ) VALUES (
        r.subject_agent_id,
        r.issuer_did,
        1,
        CASE WHEN r.asset = 'TRX' THEN r.amount ELSE 0 END,
        CASE WHEN r.asset IN ('USDT', 'USDC', 'TUSD', 'USDD') THEN r.amount ELSE 0 END,
        r.tx_timestamp,
        r.tx_timestamp
    )
    ON CONFLICT (agent_id, counterparty_did)
    DO UPDATE SET
        receipt_count = tron_receipt_counterparties.receipt_count + 1,
        total_volume_trx = tron_receipt_counterparties.total_volume_trx + 
            CASE WHEN r.asset = 'TRX' THEN r.amount ELSE 0 END,
        total_volume_usdt = tron_receipt_counterparties.total_volume_usdt + 
            CASE WHEN r.asset IN ('USDT', 'USDC', 'TUSD', 'USDD') THEN r.amount ELSE 0 END,
        last_receipt_at = GREATEST(tron_receipt_counterparties.last_receipt_at, r.tx_timestamp);

END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_tron_counterparty_stats IS 'Updates aggregated counterparty stats for trust scoring';

-- Trigger function to auto-update stats on verification
CREATE OR REPLACE FUNCTION on_tron_receipt_verified()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.verified = TRUE AND OLD.verified = FALSE THEN
        -- Update counterparty stats
        PERFORM update_tron_counterparty_stats(NEW.receipt_id);
        
        -- Attach to VAC if subject_agent_id is set
        IF NEW.subject_agent_id IS NOT NULL THEN
            PERFORM attach_tron_receipt_to_vac(NEW.receipt_id, NEW.subject_agent_id);
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger
DROP TRIGGER IF EXISTS trigger_tron_receipt_verified ON tron_receipts;
CREATE TRIGGER trigger_tron_receipt_verified
    AFTER UPDATE ON tron_receipts
    FOR EACH ROW
    WHEN (NEW.verified = TRUE AND OLD.verified = FALSE)
    EXECUTE FUNCTION on_tron_receipt_verified();

-- ============================================================
-- API ENDPOINT REGISTRY
-- ============================================================

-- Add TRON to AIP supported rails
CREATE TABLE IF NOT EXISTS aip_supported_rails (
    rail_id VARCHAR(50) PRIMARY KEY,
    rail_type VARCHAR(50) NOT NULL,
    rail_name VARCHAR(100) NOT NULL,
    description TEXT,
    protocols TEXT[], -- e.g., ['tron:trc20', 'tron:native']
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO aip_supported_rails (rail_id, rail_type, rail_name, protocols, description)
VALUES 
    ('tron', 'blockchain', 'TRON', ARRAY['tron', 'tron:trc20', 'tron:native'], 'TRON blockchain with TRC-20 support')
ON CONFLICT (rail_id) DO UPDATE SET
    protocols = EXCLUDED.protocols,
    description = EXCLUDED.description;

-- ============================================================
-- WEBHOOK EVENT TYPES
-- ============================================================

-- Add TRON-specific webhook events
INSERT INTO webhook_registry (webhook_id, entity_id, entity_type, url, events)
SELECT 
    'webhook_tron_events',
    'system',
    'system',
    'https://api.observerprotocol.org/webhooks/tron',
    '["tron.receipt.received", "tron.receipt.verified", "tron.receipt.expired"]'
WHERE NOT EXISTS (
    SELECT 1 FROM webhook_registry WHERE entity_id = 'system' AND events @> '["tron.receipt.received"]'
);
