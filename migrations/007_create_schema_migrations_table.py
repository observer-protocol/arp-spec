"""
Migration 007: Create schema_migrations tracking table with 001-006 backfill

This migration establishes the schema_migrations table to track which migrations
have been applied to the database, and backfills records for migrations 001-006
which were applied before this tracking system existed.

FUTURE MIGRATION CONVENTION (008+):
-----------------------------------
All future migrations should follow this pattern:

1. At the top of the migration script, check if already applied:
   
   with conn.cursor() as cur:
       cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", ('008',))
       if cur.fetchone():
           print("Migration 008 already applied, skipping")
           return

2. Do the migration work within a transaction

3. At the end, record the migration:
   
   cur.execute(
       '''INSERT INTO schema_migrations 
          (version, name, applied_by, checksum, notes) 
          VALUES (%s, %s, %s, %s, %s)
          ON CONFLICT (version) DO NOTHING''',
       ('008', 'migration_name', os.environ.get('USER', 'unknown'), 
        compute_sha256(__file__), None)
   )

This ensures idempotency (safe to re-run) and complete audit trail.
"""

import os
import hashlib
import psycopg2
from datetime import datetime
from pathlib import Path


def compute_sha256(file_path):
    """Compute SHA-256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for byte_block in iter(lambda: f.read(4096), b''):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_git_commit_date(file_path):
    """Get the commit date of a file from git history."""
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%ci', '--', file_path],
            capture_output=True, text=True, cwd='/media/nvme/observer-protocol'
        )
        if result.returncode == 0 and result.stdout.strip():
            date_str = result.stdout.strip()
            # Parse ISO format date
            return datetime.fromisoformat(date_str.replace(' ', 'T').replace(' +', '+'))
    except Exception:
        pass
    return None


def get_file_mtime(file_path):
    """Get file modification time."""
    try:
        stat = os.stat(file_path)
        return datetime.fromtimestamp(stat.st_mtime)
    except Exception:
        return None


def migrate(conn):
    """Execute migration 007."""
    cursor = conn.cursor()
    
    try:
        # Step 1: Create schema_migrations table
        print("Creating schema_migrations table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                applied_by  TEXT,
                checksum    TEXT,
                notes       TEXT
            )
        """)
        print("  ✓ Table created (or already exists)")
        
        # Step 2: Backfill migrations 001-003 using git commit dates
        print("\nBackfilling migrations 001-003 (from git commit dates)...")
        
        migrations_001_003 = [
            ('001', '001_initial_schema.sql'),
            ('002', '002_add_agent_tables.sql'),
            ('003', '003_replace_partner_attestations_for_vc.py'),
        ]
        
        for version, filename in migrations_001_003:
            file_path = Path('/media/nvme/observer-protocol/migrations') / filename
            
            # Try git commit date first
            applied_at = get_git_commit_date(file_path)
            notes = 'backfilled_apr22_from_git_commit_date'
            
            if not applied_at:
                # Fallback to file mtime
                applied_at = get_file_mtime(file_path)
                notes = 'backfilled_apr22_from_file_mtime'
            
            if not applied_at:
                # Last resort: use a reasonable past date
                applied_at = datetime(2026, 4, 1, 0, 0, 0)
                notes = 'backfilled_apr22_from_estimated_date'
            
            # Compute checksum if file exists
            checksum = None
            if file_path.exists():
                checksum = compute_sha256(file_path)
            
            cursor.execute("""
                INSERT INTO schema_migrations 
                (version, name, applied_at, applied_by, checksum, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (version) DO NOTHING
            """, (
                version,
                filename,
                applied_at,
                'maxi_backfill_apr22',
                checksum,
                notes
            ))
            
            print(f"  ✓ Migration {version}: {filename} (applied_at: {applied_at.isoformat()})")
        
        # Step 3: Backfill migrations 004-006 using file mtime (applied during TRON demo night)
        print("\nBackfilling migrations 004-006 (from file mtime - TRON demo night)...")
        
        migrations_004_006 = [
            ('004', '004_replace_delegation_credentials_for_recursive_model.py'),
            ('005', '005_add_revocation_tracking.py'),
            ('006', '006_replace_vac_revocation_registry_for_status_lists.py'),
        ]
        
        for version, filename in migrations_004_006:
            file_path = Path('/media/nvme/observer-protocol/migrations') / filename
            
            # Use file mtime (when file was created/modified on disk)
            applied_at = get_file_mtime(file_path)
            notes = 'backfilled_apr22_from_file_mtime'
            
            if not applied_at:
                # Fallback: use TRON demo night date (April 21, 2026)
                applied_at = datetime(2026, 4, 21, 20, 0, 0)
                notes = 'backfilled_apr22_from_estimated_date'
            
            # Compute checksum if file exists
            checksum = None
            if file_path.exists():
                checksum = compute_sha256(file_path)
            
            cursor.execute("""
                INSERT INTO schema_migrations 
                (version, name, applied_at, applied_by, checksum, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (version) DO NOTHING
            """, (
                version,
                filename,
                applied_at,
                'maxi_backfill_apr22',
                checksum,
                notes
            ))
            
            print(f"  ✓ Migration {version}: {filename} (applied_at: {applied_at.isoformat()})")
        
        # Step 4: Self-record migration 007
        print("\nRecording migration 007 (self)...")
        
        this_file = Path(__file__)
        checksum = compute_sha256(this_file) if this_file.exists() else None
        
        cursor.execute("""
            INSERT INTO schema_migrations 
            (version, name, applied_at, applied_by, checksum, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (version) DO NOTHING
        """, (
            '007',
            '007_create_schema_migrations_table.py',
            datetime.now(),
            os.environ.get('USER', 'unknown'),
            checksum,
            None  # No notes for 007 - it's the real applied time
        ))
        
        print(f"  ✓ Migration 007: {this_file.name} (applied_at: {datetime.now().isoformat()})")
        
        # Commit all changes
        conn.commit()
        print("\n✓ Migration 007 completed successfully")
        print("  - schema_migrations table created")
        print("  - Migrations 001-006 backfilled")
        print("  - Migration 007 self-recorded")
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration 007 failed: {e}")
        raise
    finally:
        cursor.close()


if __name__ == "__main__":
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        # Try to get from systemd service file
        import subprocess
        try:
            result = subprocess.run(
                ['systemctl', 'cat', 'observer-api.service'],
                capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if 'DATABASE_URL' in line and '=' in line:
                    database_url = line.split('=', 1)[1].strip()
                    break
        except Exception:
            pass
    
    if not database_url:
        # Default fallback for agentic_terminal_db
        database_url = "postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db"
    
    print(f"Connecting to database...")
    conn = psycopg2.connect(database_url)
    
    try:
        migrate(conn)
    finally:
        conn.close()
        print("\nDatabase connection closed.")