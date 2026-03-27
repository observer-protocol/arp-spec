#!/usr/bin/env python3
"""
Test VAC Quality Claims (v0.3.2)
Tests counterparty quality claims validation and notes retrieval.
"""

import sys
import os
import hashlib
import json

# Set up paths
OP_WORKSPACE_PATH = os.environ.get('OP_WORKSPACE_PATH', os.path.expanduser('~/.openclaw/workspace/observer-protocol'))
sys.path.insert(0, OP_WORKSPACE_PATH)

from partner_registry import PartnerRegistry


def test_quality_claims_validation():
    """Test quality claims validation logic."""
    print("=" * 60)
    print("Testing Quality Claims Validation")
    print("=" * 60)
    
    registry = PartnerRegistry()
    
    # Test 1: Valid complete claim
    print("\n1. Testing valid 'complete' claim...")
    valid_complete = {
        "completion_status": "complete",
        "accuracy_rating": 5,
        "dispute_raised": False,
        "payment_settled": True,
        "quality_schema_version": "0.3.2"
    }
    result = registry.validate_quality_claims(valid_complete)
    assert result["valid"] == True, f"Should be valid: {result['errors']}"
    print("   ✓ Valid complete claim accepted")
    
    # Test 2: Valid partial claim with completion_percentage
    print("\n2. Testing valid 'partial' claim with completion_percentage...")
    valid_partial = {
        "completion_status": "partial",
        "accuracy_rating": 3,
        "dispute_raised": False,
        "payment_settled": True,
        "quality_schema_version": "0.3.2",
        "completion_percentage": 75
    }
    result = registry.validate_quality_claims(valid_partial)
    assert result["valid"] == True, f"Should be valid: {result['errors']}"
    print("   ✓ Valid partial claim with percentage accepted")
    
    # Test 3: Invalid partial claim (missing completion_percentage)
    print("\n3. Testing invalid 'partial' claim (missing completion_percentage)...")
    invalid_partial = {
        "completion_status": "partial",
        "accuracy_rating": 3,
        "dispute_raised": False,
        "payment_settled": True,
        "quality_schema_version": "0.3.2"
    }
    result = registry.validate_quality_claims(invalid_partial)
    assert result["valid"] == False, "Should be invalid"
    assert any("completion_percentage" in e for e in result["errors"]), "Should error on missing percentage"
    print("   ✓ Correctly rejected partial claim without percentage")
    
    # Test 4: Invalid completion_status
    print("\n4. Testing invalid completion_status...")
    invalid_status = {
        "completion_status": "almost_done",  # Invalid
        "accuracy_rating": 4,
        "dispute_raised": False,
        "payment_settled": True,
        "quality_schema_version": "0.3.2"
    }
    result = registry.validate_quality_claims(invalid_status)
    assert result["valid"] == False, "Should be invalid"
    assert any("completion_status" in e for e in result["errors"]), "Should error on invalid status"
    print("   ✓ Correctly rejected invalid completion_status")
    
    # Test 5: Invalid accuracy_rating (out of range)
    print("\n5. Testing invalid accuracy_rating (out of range)...")
    invalid_rating = {
        "completion_status": "complete",
        "accuracy_rating": 10,  # Invalid: > 5
        "dispute_raised": False,
        "payment_settled": True,
        "quality_schema_version": "0.3.2"
    }
    result = registry.validate_quality_claims(invalid_rating)
    assert result["valid"] == False, "Should be invalid"
    assert any("accuracy_rating" in e for e in result["errors"]), "Should error on invalid rating"
    print("   ✓ Correctly rejected out-of-range accuracy_rating")
    
    # Test 6: Missing required fields
    print("\n6. Testing missing required fields...")
    missing_fields = {
        "completion_status": "complete"
        # Missing accuracy_rating, dispute_raised, payment_settled, quality_schema_version
    }
    result = registry.validate_quality_claims(missing_fields)
    assert result["valid"] == False, "Should be invalid"
    assert len(result["errors"]) >= 4, f"Should have multiple missing field errors: {result['errors']}"
    print(f"   ✓ Correctly identified {len(result['errors'])} missing fields")
    
    # Test 7: Valid claim with notes_hash
    print("\n7. Testing valid claim with notes_hash...")
    valid_with_hash = {
        "completion_status": "complete",
        "accuracy_rating": 5,
        "dispute_raised": False,
        "payment_settled": True,
        "quality_schema_version": "0.3.2",
        "notes_hash": "a" * 64  # Valid 64-char hex
    }
    result = registry.validate_quality_claims(valid_with_hash)
    assert result["valid"] == True, f"Should be valid: {result['errors']}"
    print("   ✓ Valid claim with notes_hash accepted")
    
    # Test 8: Invalid notes_hash (wrong length)
    print("\n8. Testing invalid notes_hash (wrong length)...")
    invalid_hash = {
        "completion_status": "complete",
        "accuracy_rating": 5,
        "dispute_raised": False,
        "payment_settled": True,
        "quality_schema_version": "0.3.2",
        "notes_hash": "abc123"  # Invalid: too short
    }
    result = registry.validate_quality_claims(invalid_hash)
    assert result["valid"] == False, "Should be invalid"
    assert any("notes_hash" in e for e in result["errors"]), "Should error on invalid hash"
    print("   ✓ Correctly rejected invalid notes_hash")
    
    # Test 9: Non-boolean dispute_raised
    print("\n9. Testing non-boolean dispute_raised...")
    invalid_bool = {
        "completion_status": "complete",
        "accuracy_rating": 5,
        "dispute_raised": "no",  # Invalid: string instead of boolean
        "payment_settled": True,
        "quality_schema_version": "0.3.2"
    }
    result = registry.validate_quality_claims(invalid_bool)
    assert result["valid"] == False, "Should be invalid"
    assert any("dispute_raised" in e for e in result["errors"]), "Should error on non-boolean"
    print("   ✓ Correctly rejected non-boolean dispute_raised")
    
    # Test 10: Valid claim with all optional fields
    print("\n10. Testing valid claim with all optional fields...")
    valid_full = {
        "completion_status": "partial",
        "accuracy_rating": 4,
        "dispute_raised": False,
        "payment_settled": True,
        "quality_schema_version": "0.3.2",
        "completion_percentage": 50,
        "notes_hash": "abcdef" * 10 + "abcd",  # 64 chars
        "notes_retrieval_url": "https://api.agenticterminal.ai/ars/notes/txn_123"
    }
    result = registry.validate_quality_claims(valid_full)
    assert result["valid"] == True, f"Should be valid: {result['errors']}"
    print("   ✓ Valid full claim with all optional fields accepted")
    
    print("\n" + "=" * 60)
    print("All quality claims validation tests passed!")
    print("=" * 60)
    return True


def test_notes_hash_verification():
    """Test notes hash computation and verification."""
    print("\n" + "=" * 60)
    print("Testing Notes Hash Verification")
    print("=" * 60)
    
    # Test 1: Compute hash
    print("\n1. Testing SHA256 hash computation...")
    notes_text = "The agent completed the task successfully but took longer than expected."
    computed_hash = hashlib.sha256(notes_text.encode('utf-8')).hexdigest()
    assert len(computed_hash) == 64, "Hash should be 64 characters"
    assert all(c in '0123456789abcdef' for c in computed_hash), "Hash should be hexadecimal"
    print(f"   ✓ Computed hash: {computed_hash[:16]}...")
    
    # Test 2: Same text produces same hash
    print("\n2. Testing hash consistency...")
    computed_hash2 = hashlib.sha256(notes_text.encode('utf-8')).hexdigest()
    assert computed_hash == computed_hash2, "Same text should produce same hash"
    print("   ✓ Hash is deterministic")
    
    # Test 3: Different text produces different hash
    print("\n3. Testing hash uniqueness...")
    different_text = "The agent completed the task quickly and efficiently."
    different_hash = hashlib.sha256(different_text.encode('utf-8')).hexdigest()
    assert computed_hash != different_hash, "Different text should produce different hash"
    print("   ✓ Different text produces different hash")
    
    print("\n" + "=" * 60)
    print("All notes hash verification tests passed!")
    print("=" * 60)
    return True


def test_vac_quality_claims_dataclass():
    """Test VAC QualityClaim dataclass."""
    print("\n" + "=" * 60)
    print("Testing VAC QualityClaim Dataclass")
    print("=" * 60)
    
    from vac_generator import QualityClaim
    
    # Test 1: Create minimal quality claim
    print("\n1. Testing minimal quality claim creation...")
    qc = QualityClaim(
        transaction_id="txn_123",
        completion_status="complete",
        accuracy_rating=5,
        dispute_raised=False,
        payment_settled=True,
        quality_schema_version="0.3.2"
    )
    assert qc.transaction_id == "txn_123"
    assert qc.completion_status == "complete"
    print("   ✓ Minimal quality claim created")
    
    # Test 2: Create full quality claim
    print("\n2. Testing full quality claim creation...")
    qc_full = QualityClaim(
        transaction_id="txn_456",
        completion_status="partial",
        accuracy_rating=3,
        dispute_raised=False,
        payment_settled=True,
        quality_schema_version="0.3.2",
        completion_percentage=75,
        notes_hash="a" * 64,
        notes_retrieval_url="https://example.com/notes",
        submitted_at="2026-03-27T14:00:00Z",
        partner_id="partner_789",
        partner_name="Test Partner"
    )
    assert qc_full.completion_percentage == 75
    assert qc_full.notes_hash == "a" * 64
    print("   ✓ Full quality claim created")
    
    # Test 3: Convert to dict
    print("\n3. Testing to_dict conversion...")
    qc_dict = qc_full.to_dict()
    assert "transaction_id" in qc_dict
    assert "completion_status" in qc_dict
    assert "accuracy_rating" in qc_dict
    assert "completion_percentage" in qc_dict
    assert "notes_hash" in qc_dict
    # Optional fields with None values should be omitted
    assert "submitted_at" in qc_dict
    print(f"   ✓ Dict conversion: {json.dumps(qc_dict, indent=2)[:200]}...")
    
    # Test 4: Minimal claim to_dict omits optional fields
    print("\n4. Testing minimal claim omits optional fields...")
    qc_minimal_dict = qc.to_dict()
    assert "completion_percentage" not in qc_minimal_dict  # None values omitted
    assert "notes_hash" not in qc_minimal_dict
    print("   ✓ Optional fields correctly omitted")
    
    print("\n" + "=" * 60)
    print("All VAC QualityClaim dataclass tests passed!")
    print("=" * 60)
    return True


def main():
    """Run all tests."""
    print("\n" + "#" * 60)
    print("# VAC Quality Claims Test Suite (v0.3.2)")
    print("#" * 60)
    
    all_passed = True
    
    try:
        test_quality_claims_validation()
    except Exception as e:
        print(f"\n❌ Quality claims validation tests FAILED: {e}")
        all_passed = False
    
    try:
        test_notes_hash_verification()
    except Exception as e:
        print(f"\n❌ Notes hash verification tests FAILED: {e}")
        all_passed = False
    
    try:
        test_vac_quality_claims_dataclass()
    except Exception as e:
        print(f"\n❌ VAC QualityClaim dataclass tests FAILED: {e}")
        all_passed = False
    
    print("\n" + "#" * 60)
    if all_passed:
        print("# ✅ ALL TESTS PASSED")
    else:
        print("# ❌ SOME TESTS FAILED")
    print("#" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
