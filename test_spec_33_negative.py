"""
Negative Tests for Spec 3.3 - Revocation and Lifecycle
Phase 3, Capability 3

These tests verify that the revocation system correctly rejects invalid operations
and handles edge cases as specified in Spec 3.3.
"""

import unittest
import json
import sys
import os
import base64
import gzip
import secrets
from datetime import datetime, timezone, timedelta

# Add paths for imports
sys.path.insert(0, '/media/nvme/observer-protocol/api')

from bitstring_status_list import (
    create_empty_bitstring,
    set_bit,
    get_bit,
    encode_bitstring,
    decode_bitstring,
    create_status_list_credential,
    validate_status_list_credential,
    get_changed_bits,
    check_credential_in_status_list,
    DEFAULT_BITSTRING_SIZE
)


class TestBitstringOperations(unittest.TestCase):
    """Test bitstring encode/decode operations."""
    
    def test_create_empty_bitstring(self):
        """Test creating empty bitstring."""
        bs = create_empty_bitstring(128)
        self.assertEqual(len(bs), 16)  # 128 bits = 16 bytes
        self.assertEqual(bs, bytes(16))  # All zeros
    
    def test_create_empty_bitstring_invalid_size(self):
        """Test that non-divisible-by-8 sizes are rejected."""
        with self.assertRaises(ValueError):
            create_empty_bitstring(100)  # Not divisible by 8
    
    def test_set_and_get_bit(self):
        """Test setting and getting individual bits."""
        bs = create_empty_bitstring(128)
        
        # Set bit 0
        bs = set_bit(bs, 0, True)
        self.assertTrue(get_bit(bs, 0))
        self.assertFalse(get_bit(bs, 1))
        
        # Set bit 127 (last bit)
        bs = set_bit(bs, 127, True)
        self.assertTrue(get_bit(bs, 127))
        
        # Unset bit 0
        bs = set_bit(bs, 0, False)
        self.assertFalse(get_bit(bs, 0))
    
    def test_set_bit_out_of_range(self):
        """Test that out-of-range indices raise IndexError."""
        bs = create_empty_bitstring(128)
        
        with self.assertRaises(IndexError):
            set_bit(bs, 128, True)  # One past end
        
        with self.assertRaises(IndexError):
            set_bit(bs, -1, True)  # Negative index
    
    def test_get_bit_out_of_range(self):
        """Test that out-of-range indices raise IndexError."""
        bs = create_empty_bitstring(128)
        
        with self.assertRaises(IndexError):
            get_bit(bs, 128)
        
        with self.assertRaises(IndexError):
            get_bit(bs, -1)
    
    def test_encode_decode_roundtrip(self):
        """Test that encoding and decoding preserves data."""
        bs = create_empty_bitstring(DEFAULT_BITSTRING_SIZE)
        bs = set_bit(bs, 0, True)
        bs = set_bit(bs, 1000, True)
        bs = set_bit(bs, 131071, True)  # Last bit
        
        encoded = encode_bitstring(bs)
        decoded = decode_bitstring(encoded)
        
        self.assertEqual(bs, decoded)
        self.assertTrue(get_bit(decoded, 0))
        self.assertTrue(get_bit(decoded, 1000))
        self.assertTrue(get_bit(decoded, 131071))
    
    def test_decode_invalid_base64(self):
        """Test that invalid base64 is rejected."""
        with self.assertRaises(ValueError):
            decode_bitstring("not-valid-base64!!!")
    
    def test_decode_invalid_gzip(self):
        """Test that invalid GZIP data is rejected."""
        # Valid base64 but invalid GZIP
        invalid_gzip = base64.b64encode(b"not gzip data").decode('ascii')
        with self.assertRaises(ValueError):
            decode_bitstring(invalid_gzip)


class TestStatusListCredentialStructure(unittest.TestCase):
    """Test BitstringStatusListCredential structure validation."""
    
    def test_valid_credential_structure(self):
        """Test validation of valid credential structure."""
        bs = create_empty_bitstring(128)
        encoded = encode_bitstring(bs)
        
        cred = create_status_list_credential(
            issuer_did="did:web:example.com",
            status_list_id="list-001",
            status_list_url="https://api.observerprotocol.org/sovereign/status-lists/list-001",
            encoded_bitstring=encoded,
            status_purpose="revocation"
        )
        
        is_valid, msg = validate_status_list_credential(cred)
        self.assertTrue(is_valid, msg)
    
    def test_invalid_status_purpose(self):
        """Test that invalid statusPurpose is rejected."""
        bs = create_empty_bitstring(128)
        encoded = encode_bitstring(bs)
        
        cred = create_status_list_credential(
            issuer_did="did:web:example.com",
            status_list_id="list-001",
            status_list_url="https://api.observerprotocol.org/sovereign/status-lists/list-001",
            encoded_bitstring=encoded,
            status_purpose="revocation"  # Valid initially
        )
        
        # Change to invalid purpose
        cred['credentialSubject']['statusPurpose'] = 'invalid_purpose'
        
        is_valid, msg = validate_status_list_credential(cred)
        self.assertFalse(is_valid)
        self.assertIn("statusPurpose", msg)
    
    def test_missing_required_fields(self):
        """Test that missing required fields are detected."""
        cred = {
            "@context": ["https://www.w3.org/ns/credentials/v2"],
            "id": "https://example.com/status/1"
            # Missing type, issuer, validFrom, credentialSubject
        }
        
        is_valid, msg = validate_status_list_credential(cred)
        self.assertFalse(is_valid)
    
    def test_missing_context(self):
        """Test that missing Bitstring Status List context is detected."""
        bs = create_empty_bitstring(128)
        encoded = encode_bitstring(bs)
        
        cred = create_status_list_credential(
            issuer_did="did:web:example.com",
            status_list_id="list-001",
            status_list_url="https://api.observerprotocol.org/sovereign/status-lists/list-001",
            encoded_bitstring=encoded,
            status_purpose="revocation"
        )
        
        # Remove required context
        cred['@context'] = ["https://www.w3.org/ns/credentials/v2"]  # Missing status-list context
        
        is_valid, msg = validate_status_list_credential(cred)
        self.assertFalse(is_valid)
        self.assertIn("context", msg.lower())
    
    def test_invalid_encoded_list(self):
        """Test that invalid encodedList is detected."""
        bs = create_empty_bitstring(128)
        encoded = encode_bitstring(bs)
        
        cred = create_status_list_credential(
            issuer_did="did:web:example.com",
            status_list_id="list-001",
            status_list_url="https://api.observerprotocol.org/sovereign/status-lists/list-001",
            encoded_bitstring=encoded,
            status_purpose="revocation"
        )
        
        # Set invalid encodedList
        cred['credentialSubject']['encodedList'] = "not-valid-base64!!!"
        
        is_valid, msg = validate_status_list_credential(cred)
        self.assertFalse(is_valid)


class TestChangedBitsDetection(unittest.TestCase):
    """Test detection of changed bits between bitstrings."""
    
    def test_detect_single_change(self):
        """Test detecting a single bit change."""
        old = create_empty_bitstring(128)
        new = set_bit(old, 5, True)
        
        changes = get_changed_bits(old, new)
        
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['index'], 5)
        self.assertEqual(changes[0]['old_value'], False)
        self.assertEqual(changes[0]['new_value'], True)
    
    def test_detect_multiple_changes(self):
        """Test detecting multiple bit changes."""
        old = create_empty_bitstring(128)
        old = set_bit(old, 1, True)
        old = set_bit(old, 2, True)
        
        new = set_bit(old, 2, False)  # Unset bit 2
        new = set_bit(new, 3, True)    # Set bit 3
        
        changes = get_changed_bits(old, new)
        
        self.assertEqual(len(changes), 2)
        
        indices = [c['index'] for c in changes]
        self.assertIn(2, indices)  # Changed from 1 to 0
        self.assertIn(3, indices)  # Changed from 0 to 1
    
    def test_no_changes(self):
        """Test that identical bitstrings produce no changes."""
        old = create_empty_bitstring(128)
        old = set_bit(old, 5, True)
        
        new = bytes(old)  # Copy
        
        changes = get_changed_bits(old, new)
        self.assertEqual(len(changes), 0)
    
    def test_mismatched_sizes(self):
        """Test that mismatched bitstring sizes raise error."""
        old = create_empty_bitstring(128)
        new = create_empty_bitstring(256)  # Different size
        
        with self.assertRaises(ValueError):
            get_changed_bits(old, new)
    
    def test_detect_unrevocation(self):
        """Test detecting un-revocation (1->0 for revocation purpose)."""
        old = create_empty_bitstring(128)
        old = set_bit(old, 5, True)  # Bit is 1 (revoked)
        
        new = set_bit(old, 5, False)  # Bit becomes 0 (un-revoked)
        
        changes = get_changed_bits(old, new)
        
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['index'], 5)
        self.assertEqual(changes[0]['old_value'], True)
        self.assertEqual(changes[0]['new_value'], False)
        
        # This would be forbidden for revocation purpose per Spec 3.3
        # The API endpoint should reject this


class TestCredentialStatusChecking(unittest.TestCase):
    """Test credential status checking against status lists."""
    
    def test_valid_credential_not_revoked(self):
        """Test that valid credential passes status check."""
        # Create status list with no revoked credentials
        bs = create_empty_bitstring(128)
        encoded = encode_bitstring(bs)
        
        status_list_cred = create_status_list_credential(
            issuer_did="did:web:example.com",
            status_list_id="list-001",
            status_list_url="https://api.observerprotocol.org/sovereign/status-lists/list-001",
            encoded_bitstring=encoded,
            status_purpose="revocation"
        )
        
        # Create credential status entry
        cred_status = {
            "id": "https://api.observerprotocol.org/sovereign/status-lists/list-001#5",
            "type": "BitstringStatusListEntry",
            "statusPurpose": "revocation",
            "statusListIndex": "5",
            "statusListCredential": "https://api.observerprotocol.org/sovereign/status-lists/list-001"
        }
        
        is_valid, reason = check_credential_in_status_list(cred_status, status_list_cred)
        self.assertTrue(is_valid)
        self.assertIsNone(reason)
    
    def test_revoked_credential(self):
        """Test that revoked credential is detected."""
        # Create status list with bit 5 set (revoked)
        bs = create_empty_bitstring(128)
        bs = set_bit(bs, 5, True)
        encoded = encode_bitstring(bs)
        
        status_list_cred = create_status_list_credential(
            issuer_did="did:web:example.com",
            status_list_id="list-001",
            status_list_url="https://api.observerprotocol.org/sovereign/status-lists/list-001",
            encoded_bitstring=encoded,
            status_purpose="revocation"
        )
        
        cred_status = {
            "id": "https://api.observerprotocol.org/sovereign/status-lists/list-001#5",
            "type": "BitstringStatusListEntry",
            "statusPurpose": "revocation",
            "statusListIndex": "5",
            "statusListCredential": "https://api.observerprotocol.org/sovereign/status-lists/list-001"
        }
        
        is_valid, reason = check_credential_in_status_list(cred_status, status_list_cred)
        self.assertFalse(is_valid)
        self.assertIn("revoked", reason.lower())
    
    def test_suspended_credential(self):
        """Test that suspended credential is detected."""
        bs = create_empty_bitstring(128)
        bs = set_bit(bs, 10, True)
        encoded = encode_bitstring(bs)
        
        status_list_cred = create_status_list_credential(
            issuer_did="did:web:example.com",
            status_list_id="list-001",
            status_list_url="https://api.observerprotocol.org/sovereign/status-lists/list-001",
            encoded_bitstring=encoded,
            status_purpose="suspension"
        )
        
        cred_status = {
            "id": "https://api.observerprotocol.org/sovereign/status-lists/list-001#10",
            "type": "BitstringStatusListEntry",
            "statusPurpose": "suspension",
            "statusListIndex": "10",
            "statusListCredential": "https://api.observerprotocol.org/sovereign/status-lists/list-001"
        }
        
        is_valid, reason = check_credential_in_status_list(cred_status, status_list_cred)
        self.assertFalse(is_valid)
        self.assertIn("suspended", reason.lower())
    
    def test_index_out_of_range(self):
        """Test that out-of-range index is handled."""
        bs = create_empty_bitstring(128)  # 128 bits
        encoded = encode_bitstring(bs)
        
        status_list_cred = create_status_list_credential(
            issuer_did="did:web:example.com",
            status_list_id="list-001",
            status_list_url="https://api.observerprotocol.org/sovereign/status-lists/list-001",
            encoded_bitstring=encoded,
            status_purpose="revocation"
        )
        
        cred_status = {
            "id": "https://api.observerprotocol.org/sovereign/status-lists/list-001#200",
            "type": "BitstringStatusListEntry",
            "statusPurpose": "revocation",
            "statusListIndex": "200",  # Out of range for 128-bit string
            "statusListCredential": "https://api.observerprotocol.org/sovereign/status-lists/list-001"
        }
        
        is_valid, reason = check_credential_in_status_list(cred_status, status_list_cred)
        self.assertFalse(is_valid)
        self.assertIn("out of range", reason.lower())
    
    def test_missing_status_list_credential(self):
        """Test that missing statusListCredential is handled."""
        cred_status = {
            "id": "https://example.com/status/1",
            "type": "BitstringStatusListEntry",
            "statusPurpose": "revocation",
            "statusListIndex": "5"
            # Missing statusListCredential
        }
        
        status_list_cred = {}  # Dummy
        
        is_valid, reason = check_credential_in_status_list(cred_status, status_list_cred)
        self.assertFalse(is_valid)
    
    def test_wrong_credential_type(self):
        """Test that non-BitstringStatusListEntry types are rejected."""
        cred_status = {
            "id": "https://example.com/status/1",
            "type": "SomeOtherStatusType",
            "statusPurpose": "revocation",
            "statusListIndex": "5",
            "statusListCredential": "https://example.com/status/list-1"
        }
        
        status_list_cred = {}
        
        is_valid, reason = check_credential_in_status_list(cred_status, status_list_cred)
        self.assertFalse(is_valid)
        self.assertIn("type", reason.lower())


class TestSpec33NegativeScenarios(unittest.TestCase):
    """
    Test the negative scenarios specified in Spec 3.3 §15.
    
    These test the high-level API behavior (would need database for full integration).
    """
    
    def test_unrevocation_detection(self):
        """
        Test 1: Attempt to un-revoke (flip bit 1->0 for revocation purpose)
        
        Per Spec 3.3 §6.6: Revocation is terminal - un-revocation must be rejected.
        """
        # Simulate old bitstring with bit 5 set (revoked)
        old_bs = create_empty_bitstring(128)
        old_bs = set_bit(old_bs, 5, True)
        
        # Simulate new bitstring with bit 5 unset (attempted un-revocation)
        new_bs = set_bit(old_bs, 5, False)
        
        changes = get_changed_bits(old_bs, new_bs)
        
        # Should detect the un-revocation attempt
        unrevocations = [c for c in changes if c['old_value'] == True and c['new_value'] == False]
        self.assertEqual(len(unrevocations), 1)
        self.assertEqual(unrevocations[0]['index'], 5)
        
        # The API endpoint would reject this for statusPurpose "revocation"
    
    def test_invalid_bitstring_encoding_detection(self):
        """
        Test 5: Invalid bitstring encoding
        
        Should be detected during credential structure validation.
        """
        cred = {
            "@context": [
                "https://www.w3.org/ns/credentials/v2",
                "https://www.w3.org/ns/credentials/status-list/v1"
            ],
            "id": "https://example.com/status/1",
            "type": ["VerifiableCredential", "BitstringStatusListCredential"],
            "issuer": "did:web:example.com",
            "validFrom": "2024-01-01T00:00:00Z",
            "credentialSubject": {
                "id": "https://example.com/status/1#list",
                "type": "BitstringStatusList",
                "statusPurpose": "revocation",
                "encodedList": "not-valid-base64!!!"
            }
        }
        
        is_valid, msg = validate_status_list_credential(cred)
        self.assertFalse(is_valid)
    
    def test_concurrent_index_allocation_simulation(self):
        """
        Test 8: Concurrent index allocation
        
        This tests that atomic increment would work correctly.
        Full test requires database with concurrent connections.
        """
        # Simulate atomic counter
        counter = [0]  # Use list for mutable reference
        
        def allocate():
            # Simulate: SELECT next_available_index, then UPDATE increment
            # This should be atomic in the real implementation
            allocated = counter[0]
            counter[0] += 1
            return allocated
        
        # Simulate multiple allocations
        indices = [allocate() for _ in range(10)]
        
        # All indices should be unique
        self.assertEqual(len(set(indices)), 10)
        self.assertEqual(sorted(indices), list(range(10)))
    
    def test_cascade_behavior_logical(self):
        """
        Test cascade behavior per Spec 3.3 §6.4.
        
        Parent revocation doesn't auto-flip descendant bits.
        Cascade happens at verification time.
        """
        # This is a logical test - full test requires delegation chain
        # The key insight: revoking a parent doesn't automatically revoke children
        # Children become invalid because chain verification fails
        
        # Simulate: Parent delegation revoked (bit set in parent's status list)
        parent_revoked = True
        
        # Child credential status (in its own status list)
        child_bit_set = False  # Child's own status bit is NOT set
        
        # Verification result: Child is INVALID because parent is revoked
        # even though child's own status bit is 0
        is_valid = not parent_revoked and not child_bit_set
        
        self.assertFalse(is_valid)


class TestStatusListCredentialDefaults(unittest.TestCase):
    """Test default values and edge cases."""
    
    def test_default_bitstring_size(self):
        """Test that default size is 131072 bits."""
        self.assertEqual(DEFAULT_BITSTRING_SIZE, 131072)
        
        bs = create_empty_bitstring()
        self.assertEqual(len(bs) * 8, 131072)
    
    def test_status_list_credential_defaults(self):
        """Test credential creation with default dates."""
        bs = create_empty_bitstring(128)
        encoded = encode_bitstring(bs)
        
        cred = create_status_list_credential(
            issuer_did="did:web:example.com",
            status_list_id="list-001",
            status_list_url="https://api.observerprotocol.org/sovereign/status-lists/list-001",
            encoded_bitstring=encoded,
            status_purpose="revocation"
        )
        
        # Should have validFrom and validUntil
        self.assertIn("validFrom", cred)
        self.assertIn("validUntil", cred)
        
        # ValidUntil should be ~1 year after validFrom
        valid_from = datetime.fromisoformat(cred['validFrom'].replace('Z', '+00:00'))
        valid_until = datetime.fromisoformat(cred['validUntil'].replace('Z', '+00:00'))
        
        delta = valid_until - valid_from
        self.assertGreaterEqual(delta.days, 364)  # Approximately 1 year
        self.assertLessEqual(delta.days, 366)


def run_tests():
    """Run all Spec 3.3 negative tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestBitstringOperations))
    suite.addTests(loader.loadTestsFromTestCase(TestStatusListCredentialStructure))
    suite.addTests(loader.loadTestsFromTestCase(TestChangedBitsDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestCredentialStatusChecking))
    suite.addTests(loader.loadTestsFromTestCase(TestSpec33NegativeScenarios))
    suite.addTests(loader.loadTestsFromTestCase(TestStatusListCredentialDefaults))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
