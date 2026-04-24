-- Migration 013: Policy engine registration and consultation log
-- Database: agentic_terminal_db
-- Spec: 3.5 — Enterprise Policy and Access Control (Hybrid)

BEGIN;

CREATE TABLE policy_engines (
  org_id INTEGER PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  engine_url TEXT NOT NULL,
  engine_public_key_did TEXT NOT NULL,
  engine_name TEXT NOT NULL,
  engine_version TEXT,
  registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  registered_by UUID REFERENCES users(id),
  is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE policy_consultation_log (
  id BIGSERIAL PRIMARY KEY,
  org_id INTEGER NOT NULL REFERENCES organizations(id),
  engine_url TEXT NOT NULL,
  request_id UUID NOT NULL,
  action_type TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('permit', 'deny', 'pending_approval', 'unavailable', 'signature_invalid')),
  policy_id TEXT,
  decision_payload JSONB NOT NULL,
  engine_signature TEXT,
  eval_duration_ms INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_policy_consult_org_time ON policy_consultation_log(org_id, created_at DESC);
CREATE INDEX idx_policy_consult_request ON policy_consultation_log(request_id);

INSERT INTO schema_migrations (version, name, applied_by, checksum, notes)
VALUES (
  '013',
  '013_create_policy_engine_tables.sql',
  'claude-spec-3.5',
  '',
  'Spec 3.5 — Policy engine registration and consultation log.'
);

COMMIT;
