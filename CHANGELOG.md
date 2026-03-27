# Changelog

All notable changes to the Observer Protocol project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Deprecated
- **api-server.py (v1) is now deprecated**. Please migrate to api-server-v2.py which includes:
  - Full VAC (Verified Agent Credential) support with partner attestations
  - Organization Registry for organizational attestations
  - Corpo integration for legal entity verification
  - Environment-based configuration (no hardcoded paths)
  - Improved cryptographic verification with challenge-response protocol
  - CORS origins configurable via `OP_ALLOWED_ORIGINS` environment variable
  - Workspace path configurable via `OP_WORKSPACE_PATH` environment variable

### Added
- Environment variable `OP_WORKSPACE_PATH` for configurable workspace path
- Environment variable `OP_ALLOWED_ORIGINS` for configurable CORS origins
- `.env.example` file documenting all required and optional environment variables

### Security
- Removed hardcoded file paths that could cause deployment failures
- Removed hardcoded CORS origins that could cause cross-origin issues in different environments

## Migration Guide: v1 → v2

### Step 1: Update Environment Variables
```bash
# Add to your .env file or environment
export OP_WORKSPACE_PATH="/path/to/observer-protocol"
export OP_ALLOWED_ORIGINS="https://yourdomain.com,https://www.yourdomain.com"
```

### Step 2: Update Deployment
Replace `api-server.py` with `api-server-v2.py` in your:
- Systemd service files
- Docker configurations
- Process managers (PM2, supervisor, etc.)

### Step 3: Verify Endpoints
Test all critical endpoints before removing v1:
```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/observer/agents/list
```

### Step 4: Remove v1
Once v2 is confirmed working, remove references to api-server.py

---

## [0.3.0] - 2026-03-XX

### Added
- VAC (Verified Agent Credential) v0.3 specification
- Partner Registry with support for:
  - Corpo partners (legal entity verification)
  - Verifier partners (identity/credential verification)
  - Counterparty partners (service relationship attestation)
  - Infrastructure partners (infrastructure providers)
- Organization Registry for organizational attestations
- Counterparty metadata anchoring to VAC credentials
- Revocation registry for credential revocation tracking

### Changed
- `legal_entity_id` moved from agent table to partner attestations (VAC v0.3)
- VAC credentials now include extensions for partner attestations and counterparty metadata

## [0.2.0] - 2026-02-XX

### Added
- Challenge-response cryptographic verification
- Agent registration with public key
- Agent verification via signed challenges
- SVG badge generation for verified agents
- Transaction submission with cryptographic signatures
- Verified events feed

### Changed
- Agent verification now requires cryptographic proof instead of manual approval

## [0.1.0] - 2026-01-XX

### Added
- Initial Observer Protocol API
- Agent registration (basic)
- Protocol metrics and signals endpoints
- Database schema for agents, events, and protocols
- Health check endpoint
