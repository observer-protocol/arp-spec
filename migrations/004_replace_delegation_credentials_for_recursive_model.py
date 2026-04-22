"""
Migration 004: Replace delegation_credentials for recursive model

Implements Spec 3.2 - Delegation Credentials (Recursive DID-to-DID Primitive)

This migration drops the existing delegation_credentials table (which was designed
for the flat-delegation model) and recreates it for the recursive model with:
- Parent delegation references for chain traversal
- Extracted delegation scope fields for query optimization
- Proper indexing for graph queries

Motivation: Spec 3.2 §8.1
"""

import os
import sys
import psycopg2

# Add parent directory to path for imports
sys.path.insert(0, '/media/nvme/observer-protocol/api')

MIGRATION_SQL = """
-- Drop existing table (no production data to preserve for recursive model)
DROP TABLE IF EXISTS delegation_credentials;

-- Create new recursive delegation credentials table
CREATE TABLE delegation_credentials (
    id                    SERIAL PRIMARY KEY,
    credential_id         TEXT UNIQUE NOT NULL,              -- the VC's id field (URL)
    issuer_did            TEXT NOT NULL,                      -- the issuer's DID
    subject_did           TEXT NOT NULL,                      -- the subject's DID
    credential_jsonld     JSONB NOT NULL,                     -- the full signed VC
    credential_url        TEXT NOT NULL,                      -- hosting URL (may equal credential_id)
    parent_delegation_id  TEXT,                               -- URL of parent delegation, null for roots
    valid_from            TIMESTAMPTZ NOT NULL,
    valid_until           TIMESTAMPTZ NOT NULL,
    enforcement_mode      TEXT NOT NULL,                      -- 'protocol_native' | 'pre_transaction_check'
    may_delegate_further  BOOLEAN NOT NULL,                   -- extracted from delegationScope
    kyb_credential_id     TEXT,                               -- optional KYB link
    cached_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_at      TIMESTAMPTZ                        -- last time signature was verified
);

-- Indexes for efficient graph traversal and queries
CREATE INDEX idx_delegations_issuer   ON delegation_credentials(issuer_did);
CREATE INDEX idx_delegations_subject  ON delegation_credentials(subject_did);
CREATE INDEX idx_delegations_parent   ON delegation_credentials(parent_delegation_id);
CREATE INDEX idx_delegations_validity ON delegation_credentials(valid_until);

-- Composite index for chain lookup queries
CREATE INDEX idx_delegations_chain_lookup ON delegation_credentials(subject_did, valid_until DESC);

-- Partial index for root delegations (where parent is null)
CREATE INDEX idx_delegations_roots ON delegation_credentials(parent_delegation_id) 
    WHERE parent_delegation_id IS NULL;

-- Comment the table and key columns
COMMENT ON TABLE delegation_credentials IS 'Delegation credentials per Spec 3.2 - recursive DID-to-DID delegation';
COMMENT ON COLUMN delegation_credentials.credential_id IS 'The VC id field (URL) - unique identifier';
COMMENT ON COLUMN delegation_credentials.parent_delegation_id IS 'URL of parent delegation; null for root delegations';
COMMENT ON COLUMN delegation_credentials.may_delegate_further IS 'Extracted from delegationScope.may_delegate_further for query optimization';
"""

ROLLBACK_SQL = """
-- Rollback: Drop new table and restore would require recreating old schema
-- Old schema (for reference):
-- CREATE TABLE delegation_credentials (
--     id SERIAL PRIMARY KEY,
--     credential_id TEXT UNIQUE NOT NULL,
--     issuer_did TEXT NOT NULL,
--     subject_did TEXT NOT NULL,
--     credential_jsonld JSONB NOT NULL,
--     valid_from TIMESTAMPTZ NOT NULL,
--     valid_until TIMESTAMPTZ NOT NULL,
--     cached_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );

DROP TABLE IF EXISTS delegation_credentials;
"""


def get_db_connection():
    """Get PostgreSQL database connection."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        # Try common local development URLs
        for url in [
            "postgresql://postgres:postgres@localhost:5432/agentic_terminal_db",
            "postgresql://localhost:5432/agentic_terminal_db",
        ]:
            try:
                conn = psycopg2.connect(url)
                print(f"Connected using fallback URL")
                return conn
            except:
                continue
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(database_url)


def migrate():
    """Apply the migration."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print("Applying migration 004: Replace delegation_credentials for recursive model")
        cursor.execute(MIGRATION_SQL)
        conn.commit()
        print("✓ Migration applied successfully")
        
        # Verify table was created
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'delegation_credentials'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        print(f"\nTable structure:")
        for col_name, data_type in columns:
            print(f"  - {col_name}: {data_type}")
        
        # Verify indexes
        cursor.execute("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'delegation_credentials'
        """)
        indexes = cursor.fetchall()
        print(f"\nIndexes created:")
        for idx_name, idx_def in indexes:
            print(f"  - {idx_name}")
            
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"✗ Migration failed: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def rollback():
    """Rollback the migration."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print("Rolling back migration 004...")
        cursor.execute(ROLLBACK_SQL)
        conn.commit()
        print("✓ Rollback completed")
        return True
    except Exception as e:
        conn.rollback()
        print(f"✗ Rollback failed: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback()
    else:
        migrate()
