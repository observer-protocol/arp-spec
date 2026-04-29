-- Migration 018: x402 payment credentials
-- Stores X402PaymentCredential VCs issued after verifying x402 payments

CREATE TABLE IF NOT EXISTS x402_credentials (
    id SERIAL PRIMARY KEY,
    credential_id VARCHAR(200) UNIQUE NOT NULL,
    agent_id VARCHAR(100) NOT NULL,
    agent_did VARCHAR(300) NOT NULL,
    counterparty VARCHAR(300) NOT NULL,
    network VARCHAR(50) NOT NULL DEFAULT 'eip155:8453',
    asset_symbol VARCHAR(20) NOT NULL DEFAULT 'USDC',
    amount VARCHAR(50) NOT NULL,
    resource_uri TEXT,
    settlement_tx_hash VARCHAR(200),
    facilitator_verified BOOLEAN DEFAULT FALSE,
    onchain_verified BOOLEAN DEFAULT FALSE,
    discrepancy BOOLEAN DEFAULT FALSE,
    credential_json JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_x402_agent ON x402_credentials(agent_id);
CREATE INDEX idx_x402_network ON x402_credentials(network);
CREATE INDEX idx_x402_tx_hash ON x402_credentials(settlement_tx_hash);
CREATE INDEX idx_x402_created ON x402_credentials(created_at DESC);

-- Add caip10_identifiers to observer_agents for 8004 forward compatibility (Hook 1)
ALTER TABLE observer_agents ADD COLUMN IF NOT EXISTS caip10_identifiers JSONB DEFAULT '[]'::jsonb;
