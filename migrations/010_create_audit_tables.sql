-- Migration 010: Create Spec 3.4 audit tables
-- Database: agentic_terminal_db
-- Spec: 3.4 — Compliance and Audit Trails v0.2
--
-- Six tables for dual-source audit evidence:
--   agent_activity_credentials   — agent-signed activity VCs
--   counterparty_receipts        — counterparty-signed receipt VCs
--   receipt_requests             — agent pull-protocol requests
--   receipt_acknowledgments      — counterparty pull-protocol responses
--   audit_coverage_rollup        — precomputed coverage metrics
--   audit_anomalies              — detected anomalies

BEGIN;

-- 1. Agent activity credentials
CREATE TABLE agent_activity_credentials (
  id                           SERIAL PRIMARY KEY,
  credential_id                TEXT UNIQUE NOT NULL,
  agent_did                    TEXT NOT NULL,
  activity_type                TEXT NOT NULL,
  activity_timestamp           TIMESTAMPTZ NOT NULL,
  is_merkle_root               BOOLEAN NOT NULL DEFAULT FALSE,
  merkle_root_hash             TEXT,
  parent_root_credential_id    TEXT,
  counterparty_did             TEXT,
  expects_counterparty_receipt BOOLEAN NOT NULL DEFAULT FALSE,
  expected_receipt_window      INTERVAL,
  transaction_rail             TEXT,
  transaction_reference        TEXT,
  transaction_amount           DECIMAL,
  transaction_currency         TEXT,
  delegation_credential_id     TEXT,
  credential_jsonld            JSONB NOT NULL,
  ingested_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_activity_agent        ON agent_activity_credentials(agent_did, activity_timestamp DESC);
CREATE INDEX idx_activity_type         ON agent_activity_credentials(activity_type);
CREATE INDEX idx_activity_counterparty ON agent_activity_credentials(counterparty_did);
CREATE INDEX idx_activity_expects_receipt ON agent_activity_credentials(expects_counterparty_receipt, activity_timestamp)
  WHERE expects_counterparty_receipt = TRUE;
CREATE INDEX idx_activity_reference    ON agent_activity_credentials(transaction_reference);
CREATE INDEX idx_activity_merkle_root  ON agent_activity_credentials(parent_root_credential_id)
  WHERE parent_root_credential_id IS NOT NULL;

-- 2. Counterparty receipts
CREATE TABLE counterparty_receipts (
  id                           SERIAL PRIMARY KEY,
  credential_id                TEXT UNIQUE NOT NULL,
  counterparty_did             TEXT NOT NULL,
  agent_did                    TEXT NOT NULL,
  activity_type                TEXT NOT NULL,
  acknowledgment_type          TEXT NOT NULL,
  activity_timestamp           TIMESTAMPTZ NOT NULL,
  transaction_reference        TEXT,
  transaction_rail             TEXT,
  transaction_amount           DECIMAL,
  transaction_currency         TEXT,
  agent_activity_credential_id TEXT,
  in_response_to_request_id    TEXT,
  matched_activity_id          INTEGER REFERENCES agent_activity_credentials(id),
  credential_jsonld            JSONB NOT NULL,
  ingested_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_receipts_agent        ON counterparty_receipts(agent_did, activity_timestamp DESC);
CREATE INDEX idx_receipts_counterparty ON counterparty_receipts(counterparty_did);
CREATE INDEX idx_receipts_reference    ON counterparty_receipts(transaction_reference);
CREATE INDEX idx_receipts_unmatched    ON counterparty_receipts(matched_activity_id)
  WHERE matched_activity_id IS NULL;

-- 3. Receipt requests
CREATE TABLE receipt_requests (
  id                    SERIAL PRIMARY KEY,
  credential_id         TEXT UNIQUE NOT NULL,
  agent_did             TEXT NOT NULL,
  counterparty_did      TEXT NOT NULL,
  transaction_reference TEXT,
  delivery_mode         TEXT,
  credential_jsonld     JSONB NOT NULL,
  ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_receipt_requests_agent ON receipt_requests(agent_did);
CREATE INDEX idx_receipt_requests_ref   ON receipt_requests(transaction_reference);

-- 4. Receipt acknowledgments
CREATE TABLE receipt_acknowledgments (
  id                         SERIAL PRIMARY KEY,
  credential_id              TEXT UNIQUE NOT NULL,
  counterparty_did           TEXT NOT NULL,
  agent_did                  TEXT NOT NULL,
  in_response_to_request_id  TEXT NOT NULL,
  status                     TEXT NOT NULL,
  delivery_mode              TEXT,
  reject_reason              TEXT,
  credential_jsonld          JSONB NOT NULL,
  ingested_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_acks_request   ON receipt_acknowledgments(in_response_to_request_id);
CREATE INDEX idx_acks_rejected  ON receipt_acknowledgments(status) WHERE status = 'rejected';

-- 5. Coverage rollup (precomputed)
CREATE TABLE audit_coverage_rollup (
  agent_did           TEXT NOT NULL,
  window_days         INTEGER NOT NULL,
  expected_receipts   INTEGER NOT NULL,
  received_receipts   INTEGER NOT NULL,
  coverage_rate       DECIMAL,
  computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (agent_did, window_days)
);

CREATE INDEX idx_coverage_agent ON audit_coverage_rollup(agent_did);

-- 6. Anomalies
CREATE TABLE audit_anomalies (
  id              SERIAL PRIMARY KEY,
  anomaly_type    TEXT NOT NULL,
  agent_did       TEXT NOT NULL,
  org_id          INTEGER,
  severity        TEXT NOT NULL,
  payload         JSONB NOT NULL,
  detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reconciled_at   TIMESTAMPTZ,
  admin_notes     TEXT
);

CREATE INDEX idx_anomalies_org_type ON audit_anomalies(org_id, anomaly_type, detected_at DESC);
CREATE INDEX idx_anomalies_unreconciled ON audit_anomalies(detected_at)
  WHERE reconciled_at IS NULL;

-- Record migration
INSERT INTO schema_migrations (version, name, applied_by, checksum, notes)
VALUES (
  '010',
  '010_create_audit_tables.sql',
  'claude-spec-3.4',
  '',
  'Spec 3.4 — Compliance and Audit Trails v0.2. Six tables for dual-source audit.'
);

COMMIT;
