#!/usr/bin/env python3
"""
End-to-End Protocol Tests for Observer Protocol
Fix #9: Tests the full protocol flow

Tests:
- Agent registration → attestation → verification → revocation

Run with: python3 test_e2e_protocol.py
"""

import sys
import os
import json
import hashlib
import secrets

# Add the observer-protocol-repo to path
OP_REPO_PATH = os.environ.get('OP_REPO_PATH', os.path.expanduser('~/.openclaw/workspace/observer-protocol-repo'))
sys.path.insert(0, OP_REPO_PATH)

# Environment setup for tests
os.environ.setdefault('OP_REPO_PATH', OP_REPO_PATH)
os.environ.setdefault('OP_WORKSPACE_PATH', os.path.expanduser('~/.openclaw/workspace/observer-protocol'))

import psycopg2
from datetime import datetime, timedelta

# Import the modules we need to test
from crypto_verification import (
    verify_signature,
    verify_signature_simple,
    verify_ed25519_signature,
    cache_public_key,
    get_cached_public_key,
    detect_key_type,
    persist_public_key,
    sign_message_secp256k1,
    sign_message_ed25519
)
from vac_generator import VACGenerator, VACCore, VACCredential
from partner_registry import PartnerRegistry, register_corpo_partner, issue_corpo_attestation

DB_URL = "postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db"


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(DB_URL)


def generate_test_keypair(key_type='secp256k1'):
    """Generate a test keypair for signing."""
    if key_type == 'secp256k1':
        from cryptography.hazmat.primitives.asymmetric import ec
        private_key = ec.generate_private_key(ec.SECP256K1())
        public_key = private_key.public_key()
        
        # Get private key bytes
        private_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
        
        # Get public key bytes (compressed)
        from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicNumbers
        public_numbers = public_key.public_numbers()
        x = public_numbers.x
        y = public_numbers.y
        prefix = '02' if y % 2 == 0 else '03'
        public_bytes = prefix + format(x, '064x')
        
        return private_bytes.hex(), public_bytes
    
    elif key_type == 'ed25519':
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        # Get raw bytes
        private_bytes = private_key.private_bytes_raw()
        public_bytes = public_key.public_bytes_raw()
        
        return private_bytes.hex(), public_bytes.hex()
    
    raise ValueError(f"Unknown key type: {key_type}")


class TestE2EProtocolFlow:
    """End-to-end tests for the full Observer Protocol flow."""
    
    def __init__(self):
        self.test_results = []
        self.agent_id = None
        self.partner_id = None
        self.credential_id = None
        self.private_key = None
        self.public_key = None
        
    def log(self, message):
        """Log a test message."""
        print(f"  {message}")
        
    def run_all_tests(self):
        """Run all E2E tests."""
        print("=" * 70)
        print("OBSERVER PROTOCOL - END-TO-END TESTS")
        print("=" * 70)
        
        tests = [
            ("1. Agent Registration", self.test_agent_registration),
            ("2. Public Key Persistence", self.test_public_key_persistence),
            ("3. Challenge Generation", self.test_challenge_generation),
            ("4. Challenge-Response Verification", self.test_challenge_response_verification),
            ("5. Transaction Submission", self.test_transaction_submission),
            ("6. VAC Generation", self.test_vac_generation),
            ("7. Partner Registration", self.test_partner_registration),
            ("8. Partner Attestation", self.test_partner_attestation),
            ("9. VAC Revocation", self.test_vac_revocation),
            ("10. Cleanup", self.test_cleanup),
        ]
        
        passed = 0
        failed = 0
        
        for name, test_func in tests:
            print(f"\n{'─' * 70}")
            print(f"Running: {name}")
            print('─' * 70)
            try:
                test_func()
                passed += 1
                self.test_results.append((name, True, None))
                print(f"✓ {name} PASSED")
            except Exception as e:
                failed += 1
                self.test_results.append((name, False, str(e)))
                print(f"✗ {name} FAILED: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n" + "=" * 70)
        print(f"E2E TEST RESULTS: {passed} passed, {failed} failed")
        print("=" * 70)
        
        return failed == 0
    
    def test_agent_registration(self):
        """Test 1: Register a new agent."""
        # Generate test keys
        self.private_key, self.public_key = generate_test_keypair('secp256k1')
        
        # Generate agent_id from public key hash
        self.agent_id = hashlib.sha256(self.public_key.encode()).hexdigest()[:32]
        public_key_hash = hashlib.sha256(self.public_key.encode()).hexdigest()
        
        self.log(f"Generated agent_id: {self.agent_id[:16]}...")
        self.log(f"Public key type: {detect_key_type(self.public_key)}")
        
        # Insert agent into database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO observer_agents 
                (agent_id, public_key_hash, agent_name, alias, framework, legal_entity_id, verified, created_at, public_key)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                ON CONFLICT (agent_id) DO UPDATE SET
                    agent_name = EXCLUDED.agent_name,
                    public_key = EXCLUDED.public_key,
                    verified = FALSE
                RETURNING agent_id
            """, (self.agent_id, public_key_hash, "E2E Test Agent", "e2e-test", "test_framework", None, False, self.public_key))
            
            result = cursor.fetchone()
            conn.commit()
            
            assert result, "Agent registration failed"
            self.log(f"Agent registered: {result[0][:16]}...")
            
        finally:
            cursor.close()
            conn.close()
    
    def test_public_key_persistence(self):
        """Test 2: Persist public key to database."""
        # Persist the public key
        result = persist_public_key(self.agent_id, self.public_key, verified=False)
        assert result, "Public key persistence failed"
        
        # Verify it can be retrieved
        cached_key = get_cached_public_key(self.agent_id)
        assert cached_key == self.public_key, "Cached public key mismatch"
        
        self.log(f"Public key persisted and cached successfully")
    
    def test_challenge_generation(self):
        """Test 3: Generate a verification challenge."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Generate challenge
            nonce = secrets.token_hex(32)
            created_at = datetime.utcnow()
            expires_at = created_at + timedelta(seconds=300)
            
            cursor.execute("""
                INSERT INTO verification_challenges 
                (agent_id, nonce, created_at, expires_at, used)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING challenge_id
            """, (self.agent_id, nonce, created_at, expires_at, False))
            
            result = cursor.fetchone()
            conn.commit()
            
            assert result, "Challenge generation failed"
            self.challenge_id = result[0]
            self.nonce = nonce
            self.log(f"Challenge generated: {self.challenge_id}")
            self.log(f"Nonce: {nonce[:32]}...")
            
        finally:
            cursor.close()
            conn.close()
    
    def test_challenge_response_verification(self):
        """Test 4: Sign and verify challenge response."""
        # Sign the nonce
        nonce_bytes = self.nonce.encode('utf-8')
        signature = sign_message_secp256k1(nonce_bytes, self.private_key)
        
        self.log(f"Signature generated: {signature[:64]}...")
        
        # Verify the signature
        is_valid = verify_signature_simple(nonce_bytes, signature, self.public_key)
        assert is_valid, "Signature verification failed"
        
        self.log("Signature verified successfully")
        
        # Mark challenge as used and update agent to verified
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE verification_challenges
                SET used = TRUE, used_at = NOW(), signature = %s
                WHERE challenge_id = %s
            """, (signature, self.challenge_id))
            
            cursor.execute("""
                UPDATE observer_agents
                SET verified = TRUE, verified_at = NOW()
                WHERE agent_id = %s
                RETURNING agent_id
            """, (self.agent_id,))
            
            result = cursor.fetchone()
            conn.commit()
            
            assert result, "Agent verification update failed"
            self.log("Agent marked as verified")
            
        finally:
            cursor.close()
            conn.close()
    
    def test_transaction_submission(self):
        """Test 5: Submit verified transactions."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Submit a few test transactions
            transactions = [
                ("tx_hash_001", "lightning", 500, "micro"),
                ("tx_hash_002", "lightning", 5000, "small"),
                ("tx_hash_003", "ethereum", 50000, "medium"),
            ]
            
            for tx_hash, protocol, amount_sats, bucket in transactions:
                event_id = f"event-{self.agent_id[:12]}-{secrets.token_hex(8)}"
                
                # Build and sign transaction message
                timestamp = datetime.utcnow().isoformat()
                message = f"{self.agent_id}:{tx_hash}:{protocol}:{timestamp}".encode()
                signature = sign_message_secp256k1(message, self.private_key)
                
                # Verify transaction signature
                is_valid = verify_signature_simple(message, signature, self.public_key)
                assert is_valid, f"Transaction signature verification failed for {tx_hash}"
                
                metadata = json.dumps({"amount_sats": amount_sats, "event_type": "payment.executed"})
                
                cursor.execute("""
                    INSERT INTO verified_events (
                        event_id, agent_id, counterparty_id, event_type, protocol,
                        transaction_hash, time_window, amount_bucket, direction,
                        service_description, preimage, verified, created_at, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                    ON CONFLICT (event_id) DO NOTHING
                """, (
                    event_id, self.agent_id, None, "payment.executed", protocol,
                    tx_hash, timestamp[:10], bucket, "outbound", None, None, True, metadata
                ))
                
                self.log(f"Transaction submitted: {tx_hash[:20]}... ({amount_sats} sats)")
            
            conn.commit()
            self.log(f"Submitted {len(transactions)} transactions")
            
        finally:
            cursor.close()
            conn.close()
    
    def test_vac_generation(self):
        """Test 6: Generate VAC credential."""
        # We need signing keys for VAC generation
        # For testing, we'll set a temporary OP_SIGNING_KEY
        test_op_private, test_op_public = generate_test_keypair('secp256k1')
        os.environ['OP_SIGNING_KEY'] = test_op_private
        os.environ['OP_PUBLIC_KEY'] = test_op_public
        
        generator = VACGenerator()
        
        # Generate VAC
        vac = generator.generate_vac(self.agent_id, include_extensions=True)
        
        assert vac is not None, "VAC generation failed"
        assert vac.credential_id is not None, "VAC credential_id is missing"
        assert vac.signature is not None, "VAC signature is missing"
        
        self.credential_id = vac.credential_id
        
        self.log(f"VAC generated: {vac.credential_id}")
        self.log(f"Total transactions: {vac.core.total_transactions}")
        self.log(f"Total volume (sats): {vac.core.total_volume_sats}")
        self.log(f"Unique counterparties: {vac.core.unique_counterparties}")
        
        # Verify the VAC signature
        is_valid = generator.verify_vac(vac)
        assert is_valid, "VAC signature verification failed"
        
        self.log("VAC signature verified successfully")
    
    def test_partner_registration(self):
        """Test 7: Register a partner."""
        registry = PartnerRegistry()
        
        # Generate partner keys
        partner_private, partner_public = generate_test_keypair('secp256k1')
        
        # Register partner
        result = registry.register_partner(
            partner_name=f"E2E Test Partner {secrets.token_hex(4)}",
            partner_type='verifier',
            public_key=partner_public,
            webhook_url="https://example.com/webhook",
            metadata={"test": True}
        )
        
        assert result is not None, "Partner registration failed"
        assert "partner_id" in result, "Partner ID missing from result"
        
        self.partner_id = result["partner_id"]
        self.partner_private_key = partner_private
        self.partner_public_key = partner_public
        
        self.log(f"Partner registered: {self.partner_id}")
        self.log(f"Partner type: {result['partner_type']}")
    
    def test_partner_attestation(self):
        """Test 8: Issue a partner attestation."""
        registry = PartnerRegistry()
        
        # Create attestation claims
        claims = {
            "verification_level": "basic",
            "verified_at": datetime.utcnow().isoformat(),
            "test_claim": True
        }
        
        # Create attestation hash for signing
        attestation_data = {
            "partner_id": self.partner_id,
            "agent_id": self.agent_id,
            "claims": claims,
            "issued_at": datetime.utcnow().isoformat()
        }
        attestation_hash = hashlib.sha256(
            json.dumps(attestation_data, sort_keys=True).encode()
        ).hexdigest()
        
        # Sign the attestation
        attestation_hash_bytes = bytes.fromhex(attestation_hash)
        signature = sign_message_secp256k1(attestation_hash_bytes, self.partner_private_key)
        
        # Issue attestation
        result = registry.issue_attestation(
            partner_id=self.partner_id,
            agent_id=self.agent_id,
            claims=claims,
            credential_id=self.credential_id,
            expires_in_days=30,
            attestation_signature=signature
        )
        
        assert result is not None, "Attestation issuance failed"
        assert "attestation_id" in result, "Attestation ID missing"
        
        self.attestation_id = result["attestation_id"]
        
        self.log(f"Attestation issued: {self.attestation_id}")
        self.log(f"Attestation hash: {result['attestation_hash'][:32]}...")
        
        # Retrieve attestations for agent
        attestations = registry.get_attestations_for_agent(self.agent_id)
        assert len(attestations) > 0, "No attestations found for agent"
        
        self.log(f"Retrieved {len(attestations)} attestation(s) for agent")
    
    def test_vac_revocation(self):
        """Test 9: Revoke VAC credential."""
        generator = VACGenerator()
        
        # Revoke the credential
        generator.revoke_vac(
            credential_id=self.credential_id,
            reason="test",
            revoked_by=self.partner_id
        )
        
        self.log(f"VAC revoked: {self.credential_id}")
        
        # Verify it's marked as revoked in database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT is_revoked, revocation_reason 
                FROM vac_credentials 
                WHERE credential_id = %s
            """, (self.credential_id,))
            
            result = cursor.fetchone()
            assert result is not None, "Credential not found"
            assert result[0] == True, "Credential not marked as revoked"
            
            self.log("Revocation confirmed in database")
            
        finally:
            cursor.close()
            conn.close()
    
    def test_cleanup(self):
        """Test 10: Clean up test data."""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Clean up test data (soft delete where possible)
            tables = [
                ("partner_attestations", "partner_id", self.partner_id),
                ("vac_revocation_registry", "credential_id", self.credential_id),
                ("vac_credentials", "credential_id", self.credential_id),
                ("verified_events", "agent_id", self.agent_id),
                ("verification_challenges", "agent_id", self.agent_id),
                ("public_keys", "agent_id", self.agent_id),
                ("partner_registry", "partner_id", self.partner_id),
                ("observer_agents", "agent_id", self.agent_id),
            ]
            
            for table, column, value in tables:
                if value:
                    try:
                        cursor.execute(f"""
                            DELETE FROM {table} WHERE {column} = %s
                        """, (value,))
                        self.log(f"Cleaned up {table}")
                    except Exception as e:
                        self.log(f"Note: Could not clean up {table}: {e}")
            
            conn.commit()
            self.log("Test cleanup completed")
            
        finally:
            cursor.close()
            conn.close()


def run_tests():
    """Run all E2E tests."""
    tester = TestE2EProtocolFlow()
    success = tester.run_all_tests()
    
    if success:
        print("\n✓ All E2E tests passed!")
        return 0
    else:
        print("\n✗ Some E2E tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
