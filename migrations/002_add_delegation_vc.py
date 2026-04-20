import psycopg2
import os

DATABASE_URL = os.environ.get("DATABASE_URL", 
    "postgresql://observer:observer@localhost/observer_protocol")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS delegation_requests (
    id VARCHAR(64) PRIMARY KEY,
    agent_id VARCHAR(64) NOT NULL,
    agent_did TEXT NOT NULL,
    org_did TEXT NOT NULL,
    requested_by VARCHAR(64) DEFAULT 'agent-self',
    status VARCHAR(32) DEFAULT 'pending_approval',
    created_at TIMESTAMP DEFAULT NOW(),
    approved_at TIMESTAMP,
    approved_by VARCHAR(128)
);
""")

cursor.execute("""
ALTER TABLE observer_agents 
ADD COLUMN IF NOT EXISTS delegation_vc JSONB,
ADD COLUMN IF NOT EXISTS delegation_vc_present BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS org_did TEXT,
ADD COLUMN IF NOT EXISTS trust_score INTEGER DEFAULT 0;
""")

cursor.execute("""
UPDATE observer_agents SET trust_score = 58 
WHERE agent_id = '445cf40587c07d37961547b598d5bc13';
""")

cursor.execute("""
UPDATE observer_agents SET trust_score = 82, delegation_vc_present = TRUE,
org_did = 'did:web:observerprotocol.org#dataco'
WHERE agent_id = '00a292ac00d4c671dd5a29c22b29f548';
""")

conn.commit()
cursor.close()
conn.close()
print("Migration 002 complete")
