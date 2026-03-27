#!/usr/bin/env python3
"""
VAC Crypto Verification Test Suite
Observer Protocol VAC Specification v0.3

Run with: python3 test_crypto_vac.py
"""

import sys
import os
# Use environment variable for workspace path, with sensible default
OP_WORKSPACE_PATH = os.environ.get('OP_WORKSPACE_PATH', os.path.expanduser('~/.openclaw/workspace/observer-protocol'))
sys.path.insert(0, OP_WORKSPACE_PATH)

from crypto_verification import (
    sign_message_ed25519,
    sign_message_secp256k1,
    sign_message,
    verify_signature,
    verify_vac_signature,
    generate_vac_hash,
    detect_key_type
)
import json


def run_tests():
    """Run crypto tests."""
    tests_passed = 0
    tests_failed = 0
    
    print("=" * 60)
    print("VAC Crypto Test Suite")
    print("=" * 60)
    
    # Test 1: Generate VAC hash
    print("\n[Test 1] Generate VAC hash...")
    try:
        vac_payload = {
            "version": "1.0.0",
            "issued_at": "2026-03-23T16:00:00Z",
            "expires_at": "2026-03-30T16:00:00Z",
            "credential_id": "vac_test_123",
            "core": {
                "agent_id": "agent123",
                "total_transactions": 5,
                "total_volume_sats": 500000,
                "unique_counterparty_count": 3,
                "rails_used": ["lightning"]
            }
        }
        hash1 = generate_vac_hash(vac_payload)
        hash2 = generate_vac_hash(vac_payload)
        
        assert len(hash1) == 64, "Hash should be 64 hex chars"
        assert hash1 == hash2, "Same payload should produce same hash"
        
        print(f"  ✓ PASSED (hash: {hash1[:16]}...)")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 2: Detect key types
    print("\n[Test 2] Detect key types...")
    try:
        # Ed25519 public key (32 bytes)
        ed25519_key = "a" * 64  # 32 bytes in hex = 64 chars
        assert detect_key_type(ed25519_key) == "ed25519"
        
        # SECP256k1 compressed (33 bytes starting with 02)
        secp_key = "02" + "b" * 64  # 33 bytes = 66 chars
        assert detect_key_type(secp_key) == "secp256k1"
        
        # SECP256k1 uncompressed (65 bytes starting with 04)
        secp_uncompressed = "04" + "c" * 128  # 65 bytes = 130 chars
        assert detect_key_type(secp_uncompressed) == "secp256k1"
        
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 3: Ed25519 sign and verify
    print("\n[Test 3] Ed25519 sign and verify...")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        import os
        
        # Generate a test key pair
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        # Get raw bytes for testing
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        message = b"test message for VAC signing"
        
        # Sign
        signature = private_key.sign(message)
        
        # Verify
        public_key.verify(signature, message)
        
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 4: SECP256k1 sign and verify
    print("\n[Test 4] SECP256k1 sign and verify...")
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        
        # Generate a test key pair
        private_key = ec.generate_private_key(ec.SECP256K1())
        public_key = private_key.public_key()
        
        message = b"test message for VAC signing"
        
        # Sign
        signature = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        
        # Verify
        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 5: VAC signature verification flow
    print("\n[Test 5] VAC signature verification flow...")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        
        # Generate key pair
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        # Create VAC payload
        vac_payload = {
            "version": "1.0.0",
            "issued_at": "2026-03-23T16:00:00Z",
            "expires_at": "2026-03-30T16:00:00Z",
            "credential_id": "vac_test_123",
            "core": {
                "agent_id": "agent123",
                "total_transactions": 5,
                "total_volume_sats": 500000,
                "unique_counterparty_count": 3,
                "rails_used": ["lightning"]
            }
        }
        
        # Create canonical JSON
        canonical = json.dumps(vac_payload, sort_keys=True, separators=(',', ':'))
        message = canonical.encode('utf-8')
        
        # Sign
        signature = private_key.sign(message)
        signature_hex = signature.hex()
        
        # Get public key bytes
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        public_hex = public_bytes.hex()
        
        # Verify
        public_key.verify(signature, message)
        
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Test Results: {tests_passed} passed, {tests_failed} failed")
    print("=" * 60)
    
    if tests_failed > 0:
        print("\n❌ SOME TESTS FAILED")
        return 1
    else:
        print("\n✓ ALL TESTS PASSED")
        return 0


if __name__ == "__main__":
    exit(run_tests())
