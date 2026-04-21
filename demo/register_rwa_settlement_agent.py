#!/usr/bin/env python3
"""
RWA Settlement Agent Registration Script

Registers a dedicated agent for the 4-act TRON demo flow representing a 
real-world asset settlement scenario.

Usage:
    export DATABASE_URL="postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db"
    python demo/register_rwa_settlement_agent.py

The RWA Settlement Agent will be registered with:
- Alias: "RWA-Settlement-Demo"
- DID: did:web:observerprotocol.org:agents:<uuid>
- Org affiliation: Observer Protocol Demo
- Description: "Real-world asset settlement demonstration agent for live USDC transfer workflows"
"""

import os
import sys
import json
import uuid
import base58
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api'))

import psycopg2
import psycopg2.extras
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Import OP's DID document builder
from did_document_builder import build_agent_did, build_agent_did_document

# Demo agent configuration
RWA_AGENT = {
    "agent_id": "rwa-settlement-demo-agent",
    "alias": "RWA-Settlement-Demo",
    "description": "Real-world asset settlement demonstration agent for live USDC transfer workflows",
    "org_affiliation": "Observer Protocol Demo",
    "wallet_standard": "standard",
    "chains": ["tron", "evm"],
    "verified": True
}

# Database connection
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db")


def get_db_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def generate_ed25519_keypair():
    """Generate a new Ed25519 key pair for the agent"""
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes_raw()
    public_bytes = private_key.public_key().public_bytes_raw()
    return private_bytes.hex(), public_bytes.hex()


def check_agent_exists(agent_id: str) -> bool:
    """Check if agent already exists in observer_agents table"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT agent_id FROM observer_agents WHERE agent_id = %s LIMIT 1",
                (agent_id,)
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


def register_rwa_agent():
    """Register the RWA Settlement Agent"""
    print("=" * 70)
    print("🏦 RWA Settlement Agent Registration")
    print("=" * 70)
    print(f"\n📝 Agent Configuration:")
    print(f"   Agent ID: {RWA_AGENT['agent_id']}")
    print(f"   Alias: {RWA_AGENT['alias']}")
    print(f"   Description: {RWA_AGENT['description']}")
    print(f"   Org Affiliation: {RWA_AGENT['org_affiliation']}")
    print(f"   Chains: {', '.join(RWA_AGENT['chains'])}")

    # Check if agent already exists
    if check_agent_exists(RWA_AGENT['agent_id']):
        print(f"\nℹ️  Agent '{RWA_AGENT['agent_id']}' already exists in observer_agents")
        # Get existing agent details
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM observer_agents WHERE agent_id = %s",
                    (RWA_AGENT['agent_id'],)
                )
                agent = cur.fetchone()
                if agent:
                    print(f"\n📋 Existing Agent Details:")
                    print(f"   Agent ID: {agent['agent_id']}")
                    print(f"   DID: {agent.get('agent_did', 'N/A')}")
                    print(f"   Verified: {agent.get('verified', False)}")
                    print(f"   Created: {agent.get('created_at', 'N/A')}")
                    return agent
        finally:
            conn.close()
        return None

    # Generate Ed25519 key pair
    print(f"\n🔐 Generating Ed25519 key pair...")
    private_key_hex, public_key_hex = generate_ed25519_keypair()
    print(f"   Public Key: {public_key_hex[:40]}...")

    # Build DID and DID Document
    agent_did = build_agent_did(RWA_AGENT['agent_id'])
    did_document = build_agent_did_document(RWA_AGENT['agent_id'], public_key_hex)
    print(f"   DID: {agent_did}")

    # Register agent in database
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if agent exists in agent_keys table
            cur.execute(
                "SELECT id FROM agent_keys WHERE agent_id = %s LIMIT 1",
                (RWA_AGENT['agent_id'],)
            )
            existing = cur.fetchone()

            if existing:
                print(f"\nℹ️  Agent exists in agent_keys, updating...")
                cur.execute("""
                    UPDATE agent_keys 
                    SET key_value = %s,
                        alias = %s,
                        chains = %s,
                        wallet_standard = %s,
                        verified_at = NOW()
                    WHERE agent_id = %s
                """, (public_key_hex, RWA_AGENT['alias'], 
                      json.dumps(RWA_AGENT['chains']), RWA_AGENT['wallet_standard'],
                      RWA_AGENT['agent_id']))
            else:
                print(f"\n📝 Registering agent in agent_keys...")
                cur.execute("""
                    INSERT INTO agent_keys 
                    (agent_id, key_type, key_value, chain_id, alias, chains, wallet_standard, verified_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """, (RWA_AGENT['agent_id'], 'ed25519', public_key_hex, 1, 
                      RWA_AGENT['alias'], json.dumps(RWA_AGENT['chains']),
                      RWA_AGENT['wallet_standard']))

            # Insert into observer_agents table with DID
            print(f"📝 Registering agent in observer_agents with DID...")
            cur.execute("""
                INSERT INTO observer_agents 
                (agent_id, public_key, verified, trust_score, alias, 
                 agent_did, did_document, created_at, did_updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (agent_id) DO UPDATE SET
                    public_key = EXCLUDED.public_key,
                    verified = EXCLUDED.verified,
                    alias = EXCLUDED.alias,
                    agent_did = EXCLUDED.agent_did,
                    did_document = EXCLUDED.did_document,
                    did_updated_at = NOW()
                RETURNING agent_id
            """, (RWA_AGENT['agent_id'], public_key_hex, RWA_AGENT['verified'],
                  50, RWA_AGENT['alias'], agent_did, json.dumps(did_document)))
            
            result = cur.fetchone()
            conn.commit()
            
            print(f"✅ Agent registered successfully (Agent ID: {result['agent_id']})")

    except Exception as e:
        print(f"❌ Error registering agent: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

    # Return agent details
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM observer_agents WHERE agent_id = %s",
                (RWA_AGENT['agent_id'],)
            )
            agent = cur.fetchone()
            return agent
    finally:
        conn.close()


def create_vac_credentials(agent_id: str, agent_did: str):
    """Create initial VAC credentials for the agent"""
    print(f"\n🎫 Creating VAC credentials...")
    
    try:
        from vac_generator import VACGenerator
        
        generator = VACGenerator(db_url=DATABASE_URL)
        
        # Generate VAC
        vp = generator.generate_vac(agent_id, include_extensions=True)
        
        credential_id = vp.get('id', 'N/A')
        print(f"✅ VAC created: {credential_id}")
        
        # Count credentials in VP
        vcs = vp.get('verifiableCredential', [])
        print(f"   Contains {len(vcs)} credential(s)")
        
        return vp
        
    except Exception as e:
        print(f"⚠️  Could not create VAC credentials: {e}")
        print(f"   This is normal if OP_SIGNING_KEY is not configured.")
        return None


def verify_agent_setup(agent_id: str):
    """Verify the agent is properly set up"""
    print(f"\n🔍 Verifying agent setup...")
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check observer_agents
            cur.execute(
                "SELECT * FROM observer_agents WHERE agent_id = %s",
                (agent_id,)
            )
            obs_agent = cur.fetchone()
            
            # Check agent_keys
            cur.execute(
                "SELECT * FROM agent_keys WHERE agent_id = %s",
                (agent_id,)
            )
            key_agent = cur.fetchone()
            
            # Check VAC credentials
            cur.execute(
                "SELECT COUNT(*) as vac_count FROM vac_credentials WHERE agent_id = %s AND is_revoked = FALSE",
                (agent_id,)
            )
            vac_count = cur.fetchone()['vac_count']
            
            print(f"\n📊 Verification Results:")
            print(f"   observer_agents table: {'✅' if obs_agent else '❌'}")
            print(f"   agent_keys table: {'✅' if key_agent else '❌'}")
            print(f"   VAC credentials: {'✅' if vac_count > 0 else '⚠️  None'}")
            
            if obs_agent:
                print(f"\n📋 Agent Details:")
                print(f"   Agent ID: {obs_agent['agent_id']}")
                print(f"   DID: {obs_agent.get('agent_did', 'N/A')}")
                print(f"   Verified: {obs_agent.get('verified', False)}")
                print(f"   Trust Score: {obs_agent.get('trust_score', 'N/A')}")
                print(f"   Alias: {obs_agent.get('alias', 'N/A')}")
            
            return obs_agent is not None and key_agent is not None
            
    finally:
        conn.close()


def main():
    """Main function to register the RWA Settlement Agent"""
    print("\n" + "=" * 70)
    print("  RWA SETTLEMENT AGENT REGISTRATION")
    print("  For 4-Act TRON Demo Flow")
    print("=" * 70)
    
    try:
        # Register the agent
        agent = register_rwa_agent()
        
        if agent:
            agent_id = agent['agent_id']
            agent_did = agent.get('agent_did', build_agent_did(agent_id))
            
            # Create VAC credentials
            try:
                create_vac_credentials(agent_id, agent_did)
            except Exception as e:
                print(f"\n⚠️  VAC creation skipped: {e}")
            
            # Verify setup
            verified = verify_agent_setup(agent_id)
            
            # Print summary
            print(f"\n" + "=" * 70)
            print("  REGISTRATION SUMMARY")
            print("=" * 70)
            print(f"\n✅ Agent successfully registered!")
            print(f"\n📋 Agent Details for Demo Script:")
            print(f"   Agent ID: {agent_id}")
            print(f"   DID: {agent_did}")
            print(f"   Alias: {RWA_AGENT['alias']}")
            print(f"\n🌐 Live URLs:")
            print(f"   VAC: https://observerprotocol.org/vac/{agent_id}")
            print(f"   Agent Info: https://observerprotocol.org/observer/agent/{agent_id}")
            
            # Save agent details to file
            agent_details = {
                "agent_id": agent_id,
                "did": agent_did,
                "alias": RWA_AGENT['alias'],
                "description": RWA_AGENT['description'],
                "org_affiliation": RWA_AGENT['org_affiliation'],
                "chains": RWA_AGENT['chains'],
                "verified": agent.get('verified', True),
                "trust_score": agent.get('trust_score', 50),
                "created_at": agent.get('created_at').isoformat() if agent.get('created_at') else None
            }
            
            output_file = os.path.join(os.path.dirname(__file__), 'rwa-agent-details.json')
            with open(output_file, 'w') as f:
                json.dump(agent_details, f, indent=2)
            print(f"\n💾 Agent details saved to: {output_file}")
            
            print(f"\n" + "=" * 70)
            return agent_details
        else:
            print("\n❌ Agent registration failed")
            return None
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result else 1)
