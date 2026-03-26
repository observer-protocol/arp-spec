#!/usr/bin/env python3
"""
Database Migration: Add public_keys table for persistent key storage

This migration:
1. Creates the public_keys table
2. Migrates any existing in-memory keys from _PUBLIC_KEY_CACHE
3. Adds indexes for efficient lookups

Run: python migrations/001_add_public_keys_table.py
"""

import psycopg2
import sys
import os

# Add parent directory to path to import crypto_verification
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from crypto_verification import _PUBLIC_KEY_CACHE

DB_URL = "postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db"


def run_migration():
    """Run the migration to create public_keys table."""
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    
    try:
        print("Starting migration: Add public_keys table...")
        
        # Create public_keys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS public_keys (
                id SERIAL PRIMARY KEY,
                pubkey TEXT NOT NULL,
                pubkey_hash TEXT NOT NULL UNIQUE,
                agent_id TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                verified BOOLEAN DEFAULT FALSE
            )
        """)
        print("✓ Created public_keys table")
        
        # Add indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_public_keys_pubkey 
            ON public_keys(pubkey)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_public_keys_pubkey_hash 
            ON public_keys(pubkey_hash)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_public_keys_agent_id 
            ON public_keys(agent_id)
        """)
        print("✓ Created indexes on pubkey, pubkey_hash, and agent_id")
        
        # Migrate existing in-memory keys if any
        if _PUBLIC_KEY_CACHE:
            print(f"Found {len(_PUBLIC_KEY_CACHE)} keys in memory cache to migrate...")
            migrated = 0
            
            for agent_id, cache_data in _PUBLIC_KEY_CACHE.items():
                try:
                    # Handle both old format (string) and new format (dict)
                    if isinstance(cache_data, dict):
                        public_key = cache_data.get('public_key')
                    else:
                        public_key = cache_data
                    
                    if not public_key:
                        continue
                    
                    # Calculate hash
                    import hashlib
                    pubkey_hash = hashlib.sha256(public_key.encode()).hexdigest()
                    
                    # Insert into database
                    cursor.execute("""
                        INSERT INTO public_keys (pubkey, pubkey_hash, agent_id, verified)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (pubkey_hash) DO NOTHING
                    """, (public_key, pubkey_hash, agent_id, True))
                    
                    migrated += 1
                    
                except Exception as e:
                    print(f"  Warning: Failed to migrate key for agent {agent_id}: {e}")
            
            print(f"✓ Migrated {migrated} keys from in-memory cache")
        else:
            print("No in-memory keys to migrate")
        
        # Also migrate keys from observer_agents table if public_key column exists
        try:
            cursor.execute("""
                SELECT agent_id, public_key, verified 
                FROM observer_agents 
                WHERE public_key IS NOT NULL
            """)
            agents = cursor.fetchall()
            
            if agents:
                print(f"Found {len(agents)} agents with public keys to migrate...")
                migrated = 0
                
                for agent_id, public_key, verified in agents:
                    try:
                        import hashlib
                        pubkey_hash = hashlib.sha256(public_key.encode()).hexdigest()
                        
                        cursor.execute("""
                            INSERT INTO public_keys (pubkey, pubkey_hash, agent_id, verified)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (pubkey_hash) DO NOTHING
                        """, (public_key, pubkey_hash, agent_id, verified or False))
                        
                        migrated += 1
                        
                    except Exception as e:
                        print(f"  Warning: Failed to migrate key for agent {agent_id}: {e}")
                
                print(f"✓ Migrated {migrated} keys from observer_agents table")
        except psycopg2.Error as e:
            # public_key column might not exist in observer_agents
            print(f"Note: Could not migrate from observer_agents table: {e}")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Update crypto_verification.py to load keys from database")
        print("2. Update register_agent endpoint to persist keys")
        print("3. Restart the API server")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def rollback_migration():
    """Rollback the migration (drop the public_keys table)."""
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    
    try:
        print("Rolling back migration: Dropping public_keys table...")
        cursor.execute("DROP TABLE IF EXISTS public_keys CASCADE")
        conn.commit()
        print("✅ Rollback completed")
    except Exception as e:
        conn.rollback()
        print(f"❌ Rollback failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Public Keys Table Migration")
    parser.add_argument("--rollback", action="store_true", help="Rollback the migration")
    args = parser.parse_args()
    
    if args.rollback:
        rollback_migration()
    else:
        run_migration()
