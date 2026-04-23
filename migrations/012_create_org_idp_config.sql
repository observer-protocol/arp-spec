-- Migration 012: Create org_idp_config table for per-org IdP configuration
-- Database: agentic_terminal_db
-- Spec: 3.8 — SAML SSO as a Human Auth Modality

BEGIN;

CREATE TABLE org_idp_config (
  id                SERIAL PRIMARY KEY,
  org_id            INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  provider          VARCHAR(20) NOT NULL DEFAULT 'saml',
  idp_entity_id     TEXT NOT NULL,
  idp_sso_url       TEXT NOT NULL,
  idp_x509_cert     TEXT NOT NULL,
  sp_entity_id      TEXT NOT NULL,
  acs_url           TEXT NOT NULL,
  attribute_mapping JSONB NOT NULL DEFAULT '{"email": "email", "display_name": "DisplayName", "role": null}'::jsonb,
  default_role      VARCHAR(50) NOT NULL DEFAULT 'viewer',
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by        UUID REFERENCES users(id),
  UNIQUE (org_id)
);

CREATE INDEX idx_idp_config_org ON org_idp_config(org_id);

-- Add FK from users.sso_org_idp_config_id to org_idp_config.id
ALTER TABLE users
  ADD CONSTRAINT users_sso_idp_config_fk
  FOREIGN KEY (sso_org_idp_config_id) REFERENCES org_idp_config(id);

-- Record migration
INSERT INTO schema_migrations (version, name, applied_by, checksum, notes)
VALUES (
  '012',
  '012_create_org_idp_config.sql',
  'claude-spec-3.8',
  '',
  'Spec 3.8 — Per-org IdP configuration for SAML SSO.'
);

COMMIT;
