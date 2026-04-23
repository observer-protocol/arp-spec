-- Migration 011: Add SSO columns to users table
-- Database: agentic_terminal_db
-- Spec: 3.8 — SAML SSO as a Human Auth Modality

BEGIN;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS sso_subject_id TEXT,
  ADD COLUMN IF NOT EXISTS sso_provider VARCHAR(20),
  ADD COLUMN IF NOT EXISTS sso_org_idp_config_id INTEGER;

-- Index for SSO login lookup (find user by SSO subject ID within an org)
CREATE INDEX IF NOT EXISTS idx_users_sso_subject
  ON users (sso_subject_id, organization_id)
  WHERE sso_subject_id IS NOT NULL;

-- Record migration
INSERT INTO schema_migrations (version, name, applied_by, checksum, notes)
VALUES (
  '011',
  '011_add_sso_to_users.sql',
  'claude-spec-3.8',
  '',
  'Spec 3.8 — Add SSO identity columns to users table.'
);

COMMIT;
