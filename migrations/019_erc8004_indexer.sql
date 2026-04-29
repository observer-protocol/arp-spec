-- Migration 019: ERC-8004 / TRC-8004 indexer tables
-- Stores indexed on-chain state from Identity, Reputation, and Validation registries
-- on Base and TRON. Canonical truth lives on-chain; these tables are cache.

-- ── Indexed 8004 Agents (Identity Registry NFTs) ────────────
CREATE TABLE IF NOT EXISTS erc8004_agents (
    id SERIAL PRIMARY KEY,
    chain VARCHAR(20) NOT NULL,               -- 'base' or 'tron'
    chain_id VARCHAR(30) NOT NULL,            -- CAIP-2: 'eip155:8453' or 'tron:mainnet'
    token_id VARCHAR(100) NOT NULL,           -- NFT token ID
    owner_address VARCHAR(100) NOT NULL,      -- Current NFT owner (wallet address)
    registration_file_uri TEXT,               -- tokenURI pointing to registration JSON
    registration_file_json JSONB,             -- Cached registration file content
    op_did VARCHAR(300),                      -- Resolved OP DID if found in services array
    op_agent_id VARCHAR(100),                 -- Resolved OP agent_id if matched
    has_x402_support BOOLEAN DEFAULT FALSE,   -- From registration file x402Support field
    active BOOLEAN DEFAULT TRUE,              -- From registration file active field
    first_seen_block BIGINT,
    last_updated_block BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chain, token_id)
);

CREATE INDEX idx_8004_agents_chain ON erc8004_agents(chain);
CREATE INDEX idx_8004_agents_owner ON erc8004_agents(owner_address);
CREATE INDEX idx_8004_agents_op_did ON erc8004_agents(op_did);
CREATE INDEX idx_8004_agents_op_agent ON erc8004_agents(op_agent_id);

-- ── Indexed 8004 Feedback Entries (Reputation Registry) ─────
CREATE TABLE IF NOT EXISTS erc8004_feedback (
    id SERIAL PRIMARY KEY,
    chain VARCHAR(20) NOT NULL,
    chain_id VARCHAR(30) NOT NULL,
    token_id VARCHAR(100) NOT NULL,           -- The agent NFT receiving feedback
    feedback_index INTEGER,                   -- On-chain feedback array index
    provider_address VARCHAR(100),            -- Who submitted the feedback
    feedback_file_uri TEXT,                   -- Off-chain feedback file URI
    feedback_file_json JSONB,                 -- Cached feedback file content
    has_proof_of_payment BOOLEAN DEFAULT FALSE,
    proof_of_payment_hash VARCHAR(200),       -- Hash from proofOfPayment field
    matches_op_credential BOOLEAN DEFAULT FALSE, -- True if proofOfPayment matches an OP credential
    matched_op_credential_id VARCHAR(300),    -- The OP credential ID that matched
    response_count INTEGER DEFAULT 0,         -- Number of appendResponse entries
    block_number BIGINT,
    tx_hash VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chain, token_id, feedback_index)
);

CREATE INDEX idx_8004_feedback_token ON erc8004_feedback(chain, token_id);
CREATE INDEX idx_8004_feedback_matches_op ON erc8004_feedback(matches_op_credential) WHERE matches_op_credential = TRUE;
CREATE INDEX idx_8004_feedback_provider ON erc8004_feedback(provider_address);

-- ── Indexed 8004 Validation Requests/Responses (Validation Registry) ──
CREATE TABLE IF NOT EXISTS erc8004_validations (
    id SERIAL PRIMARY KEY,
    chain VARCHAR(20) NOT NULL,
    chain_id VARCHAR(30) NOT NULL,
    token_id VARCHAR(100) NOT NULL,           -- The agent NFT being validated
    request_id VARCHAR(200),                  -- On-chain validation request identifier
    requester_address VARCHAR(100),           -- Who requested validation
    validator_address VARCHAR(100),           -- Which validator was asked (or responded)
    is_op_validation BOOLEAN DEFAULT FALSE,   -- True if OP is the validator
    request_block BIGINT,
    request_tx_hash VARCHAR(200),
    -- Response fields (populated when OP responds)
    response_uri TEXT,                        -- Our credential URI
    response_tag VARCHAR(500),                -- AT-ARS score, credential summary
    response_block BIGINT,
    response_tx_hash VARCHAR(200),
    responded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chain, request_id)
);

CREATE INDEX idx_8004_validations_token ON erc8004_validations(chain, token_id);
CREATE INDEX idx_8004_validations_op ON erc8004_validations(is_op_validation) WHERE is_op_validation = TRUE;
CREATE INDEX idx_8004_validations_pending ON erc8004_validations(responded_at) WHERE responded_at IS NULL;

-- ── Indexer State (cursor tracking) ─────────────────────────
CREATE TABLE IF NOT EXISTS erc8004_indexer_state (
    id SERIAL PRIMARY KEY,
    chain VARCHAR(20) NOT NULL,
    registry_type VARCHAR(30) NOT NULL,       -- 'identity', 'reputation', 'validation'
    last_indexed_block BIGINT DEFAULT 0,
    last_indexed_at TIMESTAMPTZ,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    UNIQUE(chain, registry_type)
);

-- Initialize indexer state for Base and TRON
INSERT INTO erc8004_indexer_state (chain, registry_type, last_indexed_block)
VALUES
    ('base', 'identity', 0),
    ('base', 'reputation', 0),
    ('base', 'validation', 0),
    ('tron', 'identity', 0),
    ('tron', 'reputation', 0),
    ('tron', 'validation', 0)
ON CONFLICT (chain, registry_type) DO NOTHING;

-- ── appendResponse trigger tracking ─────────────────────────
-- Tracks progress toward the 3-partner trigger for enabling
-- appendResponse automation (item F).
CREATE TABLE IF NOT EXISTS erc8004_append_response_trigger (
    id SERIAL PRIMARY KEY,
    partner_identifier VARCHAR(300) NOT NULL,  -- Design partner DID or address
    feedback_count INTEGER DEFAULT 0,          -- Feedback entries with OP credential match
    chain VARCHAR(20) NOT NULL,
    first_match_at TIMESTAMPTZ,
    last_match_at TIMESTAMPTZ,
    UNIQUE(partner_identifier, chain)
);

-- ── Configuration flags ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS erc8004_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- appendResponse disabled by default until trigger fires
INSERT INTO erc8004_config (key, value)
VALUES ('append_response_enabled', 'false')
ON CONFLICT (key) DO NOTHING;

-- ── Agent registration file storage (pinning service) ───────
CREATE TABLE IF NOT EXISTS erc8004_agent_registrations (
    id SERIAL PRIMARY KEY,
    agent_id VARCHAR(100) UNIQUE NOT NULL,
    agent_did VARCHAR(300),
    registration_json JSONB NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_8004_registrations_agent ON erc8004_agent_registrations(agent_id);

-- ── appendResponse tracking ─────────────────────────────────
CREATE TABLE IF NOT EXISTS erc8004_append_responses (
    id SERIAL PRIMARY KEY,
    feedback_id INTEGER NOT NULL,
    credential_id VARCHAR(300),
    response_uri TEXT,
    response_hash VARCHAR(200),
    submitted_onchain BOOLEAN DEFAULT FALSE,
    tx_hash VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(feedback_id)
);

-- ── AT-ARS signal columns on existing tables ────────────────
-- Add 8004 signal columns to enable AT-ARS integration
ALTER TABLE observer_agents ADD COLUMN IF NOT EXISTS has_8004_nft_base BOOLEAN DEFAULT FALSE;
ALTER TABLE observer_agents ADD COLUMN IF NOT EXISTS has_8004_nft_tron BOOLEAN DEFAULT FALSE;
ALTER TABLE observer_agents ADD COLUMN IF NOT EXISTS erc8004_feedback_count INTEGER DEFAULT 0;
ALTER TABLE observer_agents ADD COLUMN IF NOT EXISTS erc8004_validation_count INTEGER DEFAULT 0;
ALTER TABLE observer_agents ADD COLUMN IF NOT EXISTS erc8004_op_backed_feedback BOOLEAN DEFAULT FALSE;
