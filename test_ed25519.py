#!/usr/bin/env python3
"""
Test script for Ed25519 signature verification in Observer Protocol.
Tests both hex-encoded keys and base58-encoded Solana addresses.
"""

import sys
sys.path.insert(0, '/home/futurebit/.openclaw/workspace/observer-protocol-repo')

from crypto_verification import (
    verify_ed25519_signature,
    verify_signature,
    detect_key_type,
    cache_public_key,
    get_cached_public_key,
    get_cached_key_type
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import base58
import hashlib

def generate_ed25519_keypair():
    """Generate a new Ed25519 keypair for testing."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Get raw bytes
    private_bytes = private_key.private_bytes(
        encoding=None,
        format=None,
        encryption_algorithm=None
    ) if hasattr(private_key, 'private_bytes') else None
    
    public_bytes = public_key.public_bytes(
        encoding=None,
        format=None
    ) if hasattr(public_key, 'public_bytes') else public_key.public_bytes_raw()
    
    return private_key, public_key, public_bytes

def test_ed25519_verification():
    """Test Ed25519 signature verification with a known keypair."""
    print("=" * 60)
    print("TEST 1: Ed25519 Signature Verification with Known Keypair")
    print("=" * 60)
    
    # Generate a test keypair
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_key_bytes = public_key.public_bytes_raw()
    
    print(f"\nGenerated Ed25519 keypair:")
    print(f"  Public key (hex): {public_key_bytes.hex()}")
    print(f"  Public key length: {len(public_key_bytes)} bytes")
    
    # Test message
    message = b"Test challenge nonce for Observer Protocol"
    print(f"\nMessage to sign: {message.decode()}")
    
    # Sign the message
    signature = private_key.sign(message)
    print(f"\nSignature (hex): {signature.hex()}")
    print(f"Signature length: {len(signature)} bytes")
    
    # Verify using our function
    is_valid = verify_ed25519_signature(
        message,
        signature.hex(),
        public_key_bytes.hex()
    )
    
    print(f"\nVerification result: {'✅ PASSED' if is_valid else '❌ FAILED'}")
    
    # Test with wrong message
    wrong_message = b"Wrong message"
    is_invalid = verify_ed25519_signature(
        wrong_message,
        signature.hex(),
        public_key_bytes.hex()
    )
    print(f"Wrong message test: {'✅ PASSED (correctly rejected)' if not is_invalid else '❌ FAILED (should have rejected)'}")
    
    return is_valid and not is_invalid

def test_key_type_detection():
    """Test automatic key type detection."""
    print("\n" + "=" * 60)
    print("TEST 2: Key Type Detection")
    print("=" * 60)
    
    # Ed25519 key (32 bytes)
    ed25519_key = "a" * 64  # 32 bytes in hex = 64 chars
    ed_type = detect_key_type(ed25519_key)
    print(f"\nEd25519 key (32 bytes hex): {ed_type}")
    print(f"  Expected: ed25519, Got: {ed_type}")
    ed_pass = ed_type == 'ed25519'
    print(f"  Result: {'✅ PASSED' if ed_pass else '❌ FAILED'}")
    
    # SECP256k1 compressed (33 bytes starting with 02 or 03)
    secp_compressed = "02" + "b" * 64  # 33 bytes in hex = 66 chars
    secp_type = detect_key_type(secp_compressed)
    print(f"\nSECP256k1 compressed key: {secp_type}")
    print(f"  Expected: secp256k1, Got: {secp_type}")
    secp_pass = secp_type == 'secp256k1'
    print(f"  Result: {'✅ PASSED' if secp_pass else '❌ FAILED'}")
    
    # SECP256k1 uncompressed (65 bytes starting with 04)
    secp_uncompressed = "04" + "c" * 128  # 65 bytes in hex = 130 chars
    secp_type2 = detect_key_type(secp_uncompressed)
    print(f"\nSECP256k1 uncompressed key: {secp_type2}")
    print(f"  Expected: secp256k1, Got: {secp_type2}")
    secp2_pass = secp_type2 == 'secp256k1'
    print(f"  Result: {'✅ PASSED' if secp2_pass else '❌ FAILED'}")
    
    # Invalid key
    invalid_key = "short"
    invalid_type = detect_key_type(invalid_key)
    print(f"\nInvalid key: {invalid_type}")
    print(f"  Expected: unknown, Got: {invalid_type}")
    invalid_pass = invalid_type == 'unknown'
    print(f"  Result: {'✅ PASSED' if invalid_pass else '❌ FAILED'}")
    
    return ed_pass and secp_pass and secp2_pass and invalid_pass

def test_solana_address():
    """Test with a Solana-style base58-encoded address."""
    print("\n" + "=" * 60)
    print("TEST 3: Solana Address (Base58) Verification")
    print("=" * 60)
    
    # Generate Ed25519 keypair
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_key_bytes = public_key.public_bytes_raw()
    
    # Create base58 Solana address
    solana_address = base58.b58encode(public_key_bytes).decode('ascii')
    print(f"\nGenerated Solana address (base58): {solana_address}")
    print(f"  Address length: {len(solana_address)} chars")
    
    # Message
    message = b"Observer Protocol Solana Agent Challenge"
    print(f"\nMessage: {message.decode()}")
    
    # Sign
    signature = private_key.sign(message)
    print(f"Signature (hex): {signature.hex()[:64]}...")
    
    # Verify using base58 address
    is_valid = verify_ed25519_signature(
        message,
        signature.hex(),
        solana_address  # base58 encoded
    )
    
    print(f"\nVerification with base58 address: {'✅ PASSED' if is_valid else '❌ FAILED'}")
    
    return is_valid

def test_key_cache():
    """Test the updated key cache with type storage."""
    print("\n" + "=" * 60)
    print("TEST 4: Key Cache with Type Storage")
    print("=" * 60)
    
    # Test with Ed25519 key
    agent_id_ed = "test-agent-ed25519"
    ed25519_key = "a" * 64  # 32 bytes
    
    cache_public_key(agent_id_ed, ed25519_key)
    cached_key = get_cached_public_key(agent_id_ed)
    cached_type = get_cached_key_type(agent_id_ed)
    
    print(f"\nEd25519 key cached:")
    print(f"  Stored key: {cached_key}")
    print(f"  Detected type: {cached_type}")
    ed_pass = cached_key == ed25519_key and cached_type == 'ed25519'
    print(f"  Result: {'✅ PASSED' if ed_pass else '❌ FAILED'}")
    
    # Test with SECP256k1 key
    agent_id_secp = "test-agent-secp256k1"
    secp_key = "04" + "b" * 128  # 65 bytes uncompressed
    
    cache_public_key(agent_id_secp, secp_key)
    cached_key2 = get_cached_public_key(agent_id_secp)
    cached_type2 = get_cached_key_type(agent_id_secp)
    
    print(f"\nSECP256k1 key cached:")
    print(f"  Stored key: {cached_key2[:20]}...")
    print(f"  Detected type: {cached_type2}")
    secp_pass = cached_key2 == secp_key and cached_type2 == 'secp256k1'
    print(f"  Result: {'✅ PASSED' if secp_pass else '❌ FAILED'}")
    
    # Test legacy cache support
    agent_id_legacy = "test-agent-legacy"
    _PUBLIC_KEY_CACHE = {agent_id_legacy: "legacy_key_value"}
    
    # Manually inject into module cache
    import crypto_verification
    crypto_verification._PUBLIC_KEY_CACHE[agent_id_legacy] = "legacy_key_value"
    
    legacy_key = get_cached_public_key(agent_id_legacy)
    legacy_type = get_cached_key_type(agent_id_legacy)
    
    print(f"\nLegacy cache support:")
    print(f"  Retrieved key: {legacy_key}")
    print(f"  Detected type for legacy: {legacy_type}")
    legacy_pass = legacy_key == "legacy_key_value"
    print(f"  Result: {'✅ PASSED' if legacy_pass else '❌ FAILED'}")
    
    return ed_pass and secp_pass and legacy_pass

def test_unified_verify():
    """Test the unified verify_signature function."""
    print("\n" + "=" * 60)
    print("TEST 5: Unified verify_signature Function")
    print("=" * 60)
    
    # Generate Ed25519 keypair
    ed_private = Ed25519PrivateKey.generate()
    ed_public = ed_private.public_key()
    ed_public_bytes = ed_public.public_bytes_raw()
    
    message = b"Test message"
    ed_signature = ed_private.sign(message)
    
    # Test with Ed25519 key (should auto-detect)
    ed_valid = verify_signature(message, ed_signature.hex(), ed_public_bytes.hex())
    print(f"\nEd25519 auto-detection: {'✅ PASSED' if ed_valid else '❌ FAILED'}")
    
    return ed_valid

def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 60)
    print("OBSERVER PROTOCOL - Ed25519 SIGNATURE VERIFICATION TESTS")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("Ed25519 Verification", test_ed25519_verification()))
    except Exception as e:
        print(f"\n❌ Ed25519 Verification test failed with error: {e}")
        results.append(("Ed25519 Verification", False))
    
    try:
        results.append(("Key Type Detection", test_key_type_detection()))
    except Exception as e:
        print(f"\n❌ Key Type Detection test failed with error: {e}")
        results.append(("Key Type Detection", False))
    
    try:
        results.append(("Solana Address", test_solana_address()))
    except Exception as e:
        print(f"\n❌ Solana Address test failed with error: {e}")
        results.append(("Solana Address", False))
    
    try:
        results.append(("Key Cache", test_key_cache()))
    except Exception as e:
        print(f"\n❌ Key Cache test failed with error: {e}")
        results.append(("Key Cache", False))
    
    try:
        results.append(("Unified Verify", test_unified_verify()))
    except Exception as e:
        print(f"\n❌ Unified Verify test failed with error: {e}")
        results.append(("Unified Verify", False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {name}: {status}")
    
    all_passed = all(passed for _, passed in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED - Ed25519 support is working correctly!")
    else:
        print("❌ SOME TESTS FAILED - Please review the output above.")
    print("=" * 60)
    
    return all_passed

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
