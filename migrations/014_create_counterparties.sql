-- Migration 014: Counterparties table + auto-discovery trigger
-- Database: agentic_terminal_db
-- Spec: 3.6 — Counterparty Management (Lightweight)

BEGIN;

CREATE TABLE counterparties (
  id BIGSERIAL PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  counterparty_did TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('observed', 'accepted', 'revoked')) DEFAULT 'observed',
  tag TEXT,
  notes TEXT,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_transacted_at TIMESTAMPTZ,
  transaction_count INTEGER NOT NULL DEFAULT 0,
  accepted_at TIMESTAMPTZ,
  accepted_by UUID REFERENCES users(id),
  revoked_at TIMESTAMPTZ,
  revoked_by UUID REFERENCES users(id),
  revoke_reason TEXT,
  trust_score_cache INTEGER,
  trust_score_cached_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (org_id, counterparty_did)
);

CREATE INDEX idx_counterparties_org_status ON counterparties(org_id, status);
CREATE INDEX idx_counterparties_did ON counterparties(counterparty_did);
CREATE INDEX idx_counterparties_last_tx ON counterparties(org_id, last_transacted_at DESC NULLS LAST);

-- Auto-discovery trigger: on agent_transactions insert, upsert counterparty row
-- Uses counterparty_address column (actual column name) stored as counterparty_did
-- Looks up org via observer_agents table (actual table name)
CREATE OR REPLACE FUNCTION trg_counterparty_observe()
RETURNS TRIGGER AS $$
DECLARE
  v_org_id INTEGER;
BEGIN
  SELECT org_id INTO v_org_id FROM observer_agents WHERE agent_id = NEW.agent_id;
  IF v_org_id IS NULL THEN
    RETURN NEW;
  END IF;
  IF NEW.counterparty_address IS NULL OR NEW.counterparty_address = '' THEN
    RETURN NEW;
  END IF;

  INSERT INTO counterparties (
    org_id, counterparty_did, status, first_seen_at, last_transacted_at, transaction_count
  ) VALUES (
    v_org_id, NEW.counterparty_address, 'observed', NOW(), NOW(), 1
  )
  ON CONFLICT (org_id, counterparty_did) DO UPDATE
    SET last_transacted_at = NOW(),
        transaction_count = counterparties.transaction_count + 1,
        updated_at = NOW();

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_counterparty_observe_on_tx
AFTER INSERT ON agent_transactions
FOR EACH ROW EXECUTE FUNCTION trg_counterparty_observe();

INSERT INTO schema_migrations (version, name, applied_by, checksum, notes)
VALUES (
  '014',
  '014_create_counterparties.sql',
  'claude-spec-3.6',
  '',
  'Spec 3.6 — Counterparties table with auto-discovery trigger on agent_transactions.'
);

COMMIT;
