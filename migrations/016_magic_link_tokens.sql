-- Migration 016: Magic link tokens for chargeback prevention demo
-- Tracks issued magic link JWTs for single-use enforcement and credential retrieval

CREATE TABLE IF NOT EXISTS magic_link_tokens (
    id SERIAL PRIMARY KEY,
    jti VARCHAR(100) UNIQUE NOT NULL,
    agent_id VARCHAR(100) NOT NULL,
    agent_did VARCHAR(300),
    counterparty_did VARCHAR(300) NOT NULL,
    counterparty_name VARCHAR(200),
    transaction_context JSONB NOT NULL,
    intro TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    redeemed_at TIMESTAMPTZ,
    declined_at TIMESTAMPTZ,
    credential_json JSONB
);

CREATE INDEX idx_magic_link_jti ON magic_link_tokens(jti);
CREATE INDEX idx_magic_link_agent ON magic_link_tokens(agent_id);
CREATE INDEX idx_magic_link_expires ON magic_link_tokens(expires_at);
