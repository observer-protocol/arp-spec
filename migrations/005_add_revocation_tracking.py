"""
Migration 005: Add Revocation Tracking Columns
Spec: Spec 3.3 — Revocation and Lifecycle (Phase 3, Capability 3)

This migration adds revocation tracking columns to partner_attestations and
delegation_credentials tables for AT-side cache invalidation per Spec 3.3 §11.

The columns track when credentials were detected as revoked/suspended during
status re-checks.
"""

import os
import sys
import psycopg2

MIGRATION_SQL = """
-- Add revocation tracking columns to partner_attestations
ALTER TABLE partner_attestations
  ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMPTZ;

-- Add revocation tracking columns to delegation_credentials
ALTER TABLE delegation_credentials
  ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMPTZ;

-- Create indexes for efficient revocation queries
CREATE INDEX IF NOT EXISTS idx_partner_attestations_revoked 
    ON partner_attestations(revoked_at) 
    WHERE revoked_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_delegations_revoked 
    ON delegation_credentials(revoked_at) 
    WHERE revoked_at IS NOT NULL;

-- Create partial indexes for suspended credentials
CREATE INDEX IF NOT EXISTS idx_partner_attestations_suspended 
    ON partner_attestations(suspended_at) 
    WHERE suspended_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_delegations_suspended 
    ON delegation_credentials(suspended_at) 
    WHERE suspended_at IS NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN partner_attestations.revoked_at IS 'Timestamp when credential was detected as revoked (terminal)';
COMMENT ON COLUMN partner_attestations.suspended_at IS 'Timestamp when credential was detected as suspended (cleared when lifted)';
COMMENT ON COLUMN delegation_credentials.revoked_at IS 'Timestamp when credential was detected as revoked (terminal)';
COMMENT ON COLUMN delegation_credentials.suspended_at IS 'Timestamp when credential was detected as suspended (cleared when lifted)';
"""

ROLLBACK_SQL = """
-- Remove revocation tracking columns
ALTER TABLE partner_attestations
  DROP COLUMN IF EXISTS revoked_at,
  DROP COLUMN IF EXISTS suspended_at;

ALTER TABLE delegation_credentials
  DROP COLUMN IF EXISTS revoked_at,
  DROP COLUMN IF EXISTS suspended_at;
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
        print("Applying migration 005: Add revocation tracking columns")
        cursor.execute(MIGRATION_SQL)
        conn.commit()
        print("✓ Migration applied successfully")
        
        # Verify columns were added
        for table in ['partner_attestations', 'delegation_credentials']:
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s
                AND column_name IN ('revoked_at', 'suspended_at')
            """, (table,))
            columns = cursor.fetchall()
            print(f"\n{table} revocation columns:")
            for col_name, data_type in columns:
                print(f"  - {col_name}: {data_type}")
        
        # Verify indexes
        cursor.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename IN ('partner_attestations', 'delegation_credentials')
            AND indexname LIKE '%revoked%' OR indexname LIKE '%suspended%'
        """)
        indexes = cursor.fetchall()
        print(f"\nRevocation indexes created:")
        for (idx_name,) in indexes:
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
        print("Rolling back migration 005...")
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
