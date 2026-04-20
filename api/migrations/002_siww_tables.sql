-- SIWW (Sign-In With Wallet) Database Migration
-- Creates tables for challenge-response auth and wallet-org memberships

-- ---------------------------------------------------------------------------
-- auth_challenges: stores nonces and challenge messages for wallet signature
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS auth_challenges (
    nonce TEXT PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    wallet_type TEXT NOT NULL,
    challenge_message TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_challenges_wallet 
    ON auth_challenges (wallet_address, used_at);

CREATE INDEX IF NOT EXISTS idx_auth_challenges_expires 
    ON auth_challenges (expires_at) WHERE used_at IS NULL;

COMMENT ON TABLE auth_challenges IS 'Stores challenge nonces for SIWW (Sign-In With Wallet) authentication flow';

-- ---------------------------------------------------------------------------
-- wallet_org_memberships: links wallets to users and organizations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wallet_org_memberships (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    wallet_address TEXT NOT NULL,
    wallet_type TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    UNIQUE (wallet_address, wallet_type, org_id)
);

CREATE INDEX IF NOT EXISTS idx_wallet_memberships_lookup 
    ON wallet_org_memberships (wallet_address, wallet_type)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_wallet_memberships_user 
    ON wallet_org_memberships (user_id)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_wallet_memberships_org 
    ON wallet_org_memberships (org_id)
    WHERE revoked_at IS NULL;

COMMENT ON TABLE wallet_org_memberships IS 'Links wallets to users and orgs for SIWW authentication';

-- Verify tables were created
SELECT 'auth_challenges' as table_name, COUNT(*) as row_count FROM auth_challenges UNION ALL
SELECT 'wallet_org_memberships', COUNT(*) FROM wallet_org_memberships;
