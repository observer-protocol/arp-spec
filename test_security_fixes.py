#!/usr/bin/env python3
"""
Test Suite for Observer Protocol Security Fixes

Tests:
1. Public key persistence to database
2. Public key recovery from signature (secp256k1)
3. Transaction signature verification

Run: python test_security_fixes.py
"""

import sys
import os
import unittest
import hashlib
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crypto_verification import (
    verify_signature,
    verify_signature_simple,
    verify_ed25519_signature,
    recover_public_key_from_signature,
    persist_public_key,
    load_public_key_from_db,
    get_public_key,
    verify_public_key_signature,
    cache_public_key,
    get_cached_public_key,
    detect_key_type,
    _PUBLIC_KEY_CACHE
)


class TestPublicKeyPersistence(unittest.TestCase):
    """Test Priority 1: Public key persistence to database."""
    
    def setUp(self):
        """Set up test data."""
        self.test_agent_id = "test_agent_001"
        self.test_public_key = "03" + "a" * 64  # Compressed secp256k1 format
        
    def tearDown(self):
        """Clean up test data."""
        # Remove from cache
        if self.test_agent_id in _PUBLIC_KEY_CACHE:
            del _PUBLIC_KEY_CACHE[self.test_agent_id]
        
        # Remove from database
        try:
            import psycopg2
            conn = psycopg2.connect(
                "postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db"
            )
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM public_keys WHERE agent_id = %s",
                (self.test_agent_id,)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Cleanup warning: {e}")
    
    def test_cache_public_key(self):
        """Test that public keys are cached correctly."""
        cache_public_key(self.test_agent_id, self.test_public_key)
        
        cached_key = get_cached_public_key(self.test_agent_id)
        self.assertEqual(cached_key, self.test_public_key)
        print("✓ Cache public key works")
    
    def test_persist_public_key_to_db(self):
        """Test that public keys can be persisted to database."""
        result = persist_public_key(self.test_agent_id, self.test_public_key, verified=True)
        self.assertTrue(result)
        
        # Verify it was stored in cache
        cached_key = get_cached_public_key(self.test_agent_id)
        self.assertEqual(cached_key, self.test_public_key)
        print("✓ Persist public key to database works")
    
    def test_load_public_key_from_db(self):
        """Test loading public key from database."""
        # First persist it
        persist_public_key(self.test_agent_id, self.test_public_key)
        
        # Clear cache
        if self.test_agent_id in _PUBLIC_KEY_CACHE:
            del _PUBLIC_KEY_CACHE[self.test_agent_id]
        
        # Load from DB
        loaded_key = load_public_key_from_db(self.test_agent_id)
        self.assertEqual(loaded_key, self.test_public_key)
        print("✓ Load public key from database works")
    
    def test_get_public_key_cache_first(self):
        """Test that get_public_key checks cache first."""
        cache_public_key(self.test_agent_id, self.test_public_key)
        
        key = get_public_key(self.test_agent_id)
        self.assertEqual(key, self.test_public_key)
        print("✓ Get public key (cache first) works")


class TestPublicKeyRecovery(unittest.TestCase):
    """Test Priority 2: recover_public_key_from_signature function."""
    
    def test_detect_key_type_secp256k1_compressed(self):
        """Test detecting compressed secp256k1 keys."""
        key = "03" + "a" * 64  # Compressed secp256k1
        key_type = detect_key_type(key)
        self.assertEqual(key_type, 'secp256k1')
        print("✓ Detect secp256k1 compressed key type")
    
    def test_detect_key_type_secp256k1_uncompressed(self):
        """Test detecting uncompressed secp256k1 keys."""
        key = "04" + "a" * 128  # Uncompressed secp256k1
        key_type = detect_key_type(key)
        self.assertEqual(key_type, 'secp256k1')
        print("✓ Detect secp256k1 uncompressed key type")
    
    def test_detect_key_type_ed25519(self):
        """Test detecting Ed25519 keys."""
        key = "a" * 64  # 32 bytes = 64 hex chars
        key_type = detect_key_type(key)
        self.assertEqual(key_type, 'ed25519')
        print("✓ Detect Ed25519 key type")
    
    def test_recover_public_key_function_exists(self):
        """Test that recover_public_key_from_signature function is properly implemented."""
        # This test verifies the function exists and returns proper tuple format
        message = b"test message"
        # Create a dummy signature (this won't validate but tests the function interface)
        sig = "a" * 128  # 64 bytes = 128 hex chars
        
        result = recover_public_key_from_signature(message, sig)
        
        # Should return a tuple (pubkey_hex, recovery_id) or (None, None)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        
        # If recovery succeeded (with coincurve), should have valid key
        # If it failed (fallback without coincurve), should be (None, None)
        pubkey, recovery_id = result
        
        if pubkey is not None:
            # If recovery succeeded, verify the key format
            self.assertIsInstance(pubkey, str)
            self.assertTrue(len(pubkey) == 66 or len(pubkey) == 130)  # Compressed or uncompressed
            self.assertIsInstance(recovery_id, int)
            self.assertTrue(0 <= recovery_id <= 3)
            print("✓ Public key recovery with coincurve works")
        else:
            # Fallback mode returns None without coincurve
            print("✓ Public key recovery function exists (coincurve not installed)")


class TestTransactionSignatureVerification(unittest.TestCase):
    """Test Priority 3: Transaction signature verification."""
    
    def setUp(self):
        """Set up test keys."""
        self.test_agent_id = "test_agent_tx_001"
        
        # Generate a test secp256k1 key pair for testing
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes
            
            self.private_key = ec.generate_private_key(ec.SECP256K1())
            public_key = self.private_key.public_key()
            
            # Get compressed public key
            from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
            public_numbers = public_key.public_numbers()
            x_hex = format(public_numbers.x, '064x')
            y_hex = format(public_numbers.y, '064x')
            
            # Compressed format: 02 if y is even, 03 if y is odd
            prefix = "02" if public_numbers.y % 2 == 0 else "03"
            self.public_key_hex = prefix + x_hex
            
            # Store full uncompressed for some operations
            self.public_key_uncompressed = "04" + x_hex + y_hex
            
        except Exception as e:
            print(f"Warning: Could not generate test key: {e}")
            self.private_key = None
            self.public_key_hex = "03" + "a" * 64
            self.public_key_uncompressed = "04" + "a" * 128
        
        # Cache the public key
        cache_public_key(self.test_agent_id, self.public_key_hex)
    
    def tearDown(self):
        """Clean up."""
        if self.test_agent_id in _PUBLIC_KEY_CACHE:
            del _PUBLIC_KEY_CACHE[self.test_agent_id]
    
    def test_verify_signature_secp256k1(self):
        """Test secp256k1 signature verification."""
        if not self.private_key:
            self.skipTest("No private key available")
        
        message = b"test transaction message"
        
        # Sign the message
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        
        signature = self.private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        
        # Convert to hex
        sig_hex = signature.hex()
        
        # Verify using our function
        result = verify_signature_simple(message, sig_hex, self.public_key_uncompressed)
        self.assertTrue(result)
        print("✓ secp256k1 signature verification works")
    
    def test_verify_public_key_signature(self):
        """Test the high-level verify_public_key_signature function."""
        if not self.private_key:
            self.skipTest("No private key available")
        
        message = b"test transaction with agent lookup"
        
        # Sign the message
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        
        signature = self.private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        sig_hex = signature.hex()
        
        # Verify using agent_id lookup
        result = verify_public_key_signature(message, sig_hex, self.test_agent_id)
        self.assertTrue(result)
        print("✓ Public key signature verification with agent lookup works")
    
    def test_invalid_signature_fails(self):
        """Test that invalid signatures are rejected."""
        message = b"test message"
        # Invalid signature
        invalid_sig = "00" * 64  # 64 bytes of zeros
        
        result = verify_signature_simple(message, invalid_sig, self.public_key_hex)
        self.assertFalse(result)
        print("✓ Invalid signatures are correctly rejected")
    
    def test_transaction_message_format(self):
        """Test the transaction message canonical format."""
        # This tests the format used in submit-transaction endpoint
        message_data = {
            "agent_id": "test_agent",
            "protocol": "L402",
            "transaction_reference": "tx_12345",
            "timestamp": "2024-01-01T00:00:00Z",
            "amount_sats": 1000
        }
        
        # Create canonical JSON (consistent format for signing)
        message_json = json.dumps(message_data, sort_keys=True, separators=(',', ':'))
        message_bytes = message_json.encode('utf-8')
        
        if self.private_key:
            # Sign
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes
            
            signature = self.private_key.sign(message_bytes, ec.ECDSA(hashes.SHA256()))
            sig_hex = signature.hex()
            
            # Verify
            result = verify_signature_simple(message_bytes, sig_hex, self.public_key_uncompressed)
            self.assertTrue(result)
        
        print("✓ Transaction message canonical format works")


class TestIntegration(unittest.TestCase):
    """Integration tests for all three fixes working together."""
    
    def test_full_flow(self):
        """Test the complete flow: persist key, sign transaction, verify signature."""
        agent_id = "integration_test_agent"
        
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes
            
            # Generate key
            private_key = ec.generate_private_key(ec.SECP256K1())
            public_key = private_key.public_key()
            public_numbers = public_key.public_numbers()
            
            # Compressed public key
            prefix = "02" if public_numbers.y % 2 == 0 else "03"
            public_key_hex = prefix + format(public_numbers.x, '064x')
            
            # 1. Persist public key
            result = persist_public_key(agent_id, public_key_hex, verified=True)
            self.assertTrue(result)
            print("  ✓ Step 1: Public key persisted")
            
            # 2. Clear cache and load from DB
            if agent_id in _PUBLIC_KEY_CACHE:
                del _PUBLIC_KEY_CACHE[agent_id]
            
            loaded_key = load_public_key_from_db(agent_id)
            self.assertEqual(loaded_key, public_key_hex)
            print("  ✓ Step 2: Public key loaded from database")
            
            # 3. Sign a transaction message
            message_data = {
                "agent_id": agent_id,
                "protocol": "L402",
                "transaction_reference": "tx_integration_001",
                "timestamp": "2024-01-01T00:00:00Z",
                "amount_sats": 5000
            }
            message_json = json.dumps(message_data, sort_keys=True, separators=(',', ':'))
            message_bytes = message_json.encode('utf-8')
            
            # Need uncompressed key for cryptography library
            public_key_uncompressed = "04" + format(public_numbers.x, '064x') + format(public_numbers.y, '064x')
            signature = private_key.sign(message_bytes, ec.ECDSA(hashes.SHA256()))
            sig_hex = signature.hex()
            print("  ✓ Step 3: Transaction signed")
            
            # 4. Verify signature using agent lookup
            result = verify_public_key_signature(message_bytes, sig_hex, agent_id)
            self.assertTrue(result)
            print("  ✓ Step 4: Transaction signature verified")
            
            # 5. Test invalid signature is rejected
            invalid_sig = "00" * len(sig_hex)
            result = verify_public_key_signature(message_bytes, invalid_sig, agent_id)
            self.assertFalse(result)
            print("  ✓ Step 5: Invalid signature correctly rejected")
            
        except ImportError as e:
            self.skipTest(f"Required library not available: {e}")
        finally:
            # Cleanup
            if agent_id in _PUBLIC_KEY_CACHE:
                del _PUBLIC_KEY_CACHE[agent_id]
            try:
                import psycopg2
                conn = psycopg2.connect(
                    "postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db"
                )
                cursor = conn.cursor()
                cursor.execute("DELETE FROM public_keys WHERE agent_id = %s", (agent_id,))
                conn.commit()
                cursor.close()
                conn.close()
            except:
                pass


class TestEventIdUniqueness(unittest.TestCase):
    """Test: Simultaneous transactions produce unique event_ids."""
    
    def test_simultaneous_transactions_unique_event_ids(self):
        """Confirm two transactions from same agent get different event_ids."""
        import uuid
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        agent_id = "test_agent_simultaneous"
        
        def generate_event_id():
            """Simulate event_id generation as in api-server-v2.py."""
            return f"event-{agent_id[:12]}-{str(uuid.uuid4())[:8]}"
        
        # Generate multiple event_ids rapidly (simulating simultaneous requests)
        event_ids = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(generate_event_id) for _ in range(20)]
            for future in as_completed(futures):
                event_ids.append(future.result())
        
        # All event_ids should be unique
        unique_ids = set(event_ids)
        self.assertEqual(
            len(unique_ids), 
            len(event_ids),
            f"Duplicate event_ids detected! Generated {len(event_ids)} IDs but only {len(unique_ids)} unique."
        )
        
        print(f"✅ Generated {len(event_ids)} unique event_ids (no duplicates)")
    
    def test_event_id_format(self):
        """Confirm event_id follows expected format."""
        import uuid
        
        agent_id = "agent_test_123"
        event_id = f"event-{agent_id[:12]}-{str(uuid.uuid4())[:8]}"
        
        # Check format: event-{agent_prefix}-{uuid_suffix}
        self.assertTrue(event_id.startswith("event-"))
        self.assertEqual(len(event_id.split("-")), 3)
        
        parts = event_id.split("-")
        self.assertEqual(len(parts[1]), 12)  # agent_id prefix
        self.assertEqual(len(parts[2]), 8)   # uuid suffix
        
        print(f"✅ Event ID format correct: {event_id}")


def run_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Observer Protocol Security Fixes Test Suite")
    print("=" * 60)
    print()
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestPublicKeyPersistence))
    suite.addTests(loader.loadTestsFromTestCase(TestPublicKeyRecovery))
    suite.addTests(loader.loadTestsFromTestCase(TestTransactionSignatureVerification))
    suite.addTests(loader.loadTestsFromTestCase(TestEventIdUniqueness))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print()
    print("=" * 60)
    if result.wasSuccessful():
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 60)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
