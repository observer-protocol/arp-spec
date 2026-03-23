#!/usr/bin/env python3
"""
VAC (Verified Agent Credential) Simple Test Suite
Observer Protocol VAC Specification v0.3

Run with: python3 test_vac_simple.py
"""

import json
import sys
sys.path.insert(0, '/home/futurebit/.openclaw/workspace/observer-protocol')

from vac_generator import (
    VACCore,
    PartnerAttestation,
    VACExtensions,
    VACCredential,
    VAC_VERSION,
    VAC_MAX_AGE_DAYS
)


def run_tests():
    """Run all VAC tests."""
    tests_passed = 0
    tests_failed = 0
    
    print("=" * 60)
    print("VAC v0.3 Test Suite")
    print("=" * 60)
    
    # Test 1: Basic VACCore creation
    print("\n[Test 1] VACCore basic creation...")
    try:
        core = VACCore(
            agent_id="test_agent_123",
            total_transactions=10,
            total_volume_sats=1000000,
            unique_counterparties=5,
            rails_used=["lightning", "L402"]
        )
        assert core.agent_id == "test_agent_123"
        assert core.total_transactions == 10
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 2: Optional fields omitted
    print("\n[Test 2] VACCore omits optional None values...")
    try:
        core = VACCore(
            agent_id="test_agent_123",
            total_transactions=10,
            total_volume_sats=1000000,
            unique_counterparties=5,
            rails_used=["lightning"]
        )
        d = core.to_dict()
        assert "first_transaction_at" not in d
        assert "last_transaction_at" not in d
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 3: Canonical JSON sorting
    print("\n[Test 3] VACCredential canonical JSON sorts keys...")
    try:
        core = VACCore(
            agent_id="agent123",
            total_transactions=5,
            total_volume_sats=500000,
            unique_counterparties=3,
            rails_used=["lightning"]
        )
        vac = VACCredential(
            version=VAC_VERSION,
            issued_at="2026-03-23T16:00:00Z",
            expires_at="2026-03-30T16:00:00Z",
            credential_id="vac_agent123_abc123",
            core=core
        )
        canonical = vac.canonical_json()
        # Keys should be in alphabetical order
        assert canonical.index('"core"') < canonical.index('"credential_id"')
        assert canonical.index('"credential_id"') < canonical.index('"expires_at"')
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 4: No null values in output (CRITICAL CONSTRAINT)
    print("\n[Test 4] CRITICAL: No null values in output...")
    try:
        core = VACCore(
            agent_id="agent123",
            total_transactions=5,
            total_volume_sats=500000,
            unique_counterparties=3,
            rails_used=["lightning"]
        )
        vac = VACCredential(
            version=VAC_VERSION,
            issued_at="2026-03-23T16:00:00Z",
            expires_at="2026-03-30T16:00:00Z",
            credential_id="vac_agent123_abc123",
            core=core
        )
        d = vac.to_dict()
        json_str = json.dumps(d)
        assert 'null' not in json_str, f"Found null in JSON: {json_str}"
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 5: Optional fields omitted entirely
    print("\n[Test 5] CRITICAL: Optional fields omitted entirely...")
    try:
        core = VACCore(
            agent_id="agent123",
            total_transactions=5,
            total_volume_sats=500000,
            unique_counterparties=3,
            rails_used=["lightning"]
        )
        vac = VACCredential(
            version=VAC_VERSION,
            issued_at="2026-03-23T16:00:00Z",
            expires_at="2026-03-30T16:00:00Z",
            credential_id="vac_agent123_abc123",
            core=core
        )
        d = vac.to_dict()
        assert "extensions" not in d, "extensions should be omitted when None"
        assert "signature" not in d, "signature should be omitted when None"
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 6: Corpo legal_entity_id location
    print("\n[Test 6] Corpo legal_entity_id in partner_attestations.corpo.claims...")
    try:
        att = PartnerAttestation(
            partner_id="corpo-partner",
            partner_name="Corpo Legal",
            partner_type="corpo",
            claims={
                "legal_entity_id": "CORP-12345-DE",
                "jurisdiction": "Germany"
            },
            issued_at="2026-03-23T16:00:00Z"
        )
        
        ext = VACExtensions(partner_attestations=[att])
        d = ext.to_dict()
        
        # Verify structure per v0.3 spec
        assert att.partner_type == "corpo"
        assert "legal_entity_id" in d["partner_attestations"][0]["claims"]
        assert d["partner_attestations"][0]["claims"]["legal_entity_id"] == "CORP-12345-DE"
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 7: Version format
    print("\n[Test 7] VAC_VERSION format is semantic version...")
    try:
        assert VAC_VERSION.count('.') == 2
        parts = VAC_VERSION.split('.')
        assert all(p.isdigit() for p in parts)
        print(f"  ✓ PASSED (version: {VAC_VERSION})")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 8: Empty extensions returns None
    print("\n[Test 8] Empty VACExtensions returns None...")
    try:
        ext = VACExtensions()
        assert ext.to_dict() is None
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 9: Complete VAC example
    print("\n[Test 9] Complete VAC credential example...")
    try:
        core = VACCore(
            agent_id="abc123def456",
            total_transactions=42,
            total_volume_sats=1500000,
            unique_counterparties=7,
            rails_used=["lightning", "L402"],
            first_transaction_at="2026-02-01T10:00:00Z",
            last_transaction_at="2026-03-22T14:30:00Z"
        )
        
        att = PartnerAttestation(
            partner_id="550e8400-e29b-41d4-a716-446655440000",
            partner_name="Corpo Legal Services",
            partner_type="corpo",
            claims={
                "legal_entity_id": "CORP-12345-DE",
                "jurisdiction": "Germany"
            },
            issued_at="2026-03-20T10:00:00Z"
        )
        
        ext = VACExtensions(partner_attestations=[att])
        
        vac = VACCredential(
            version=VAC_VERSION,
            issued_at="2026-03-23T16:00:00Z",
            expires_at="2026-03-30T16:00:00Z",
            credential_id="vac_abc123def456_7a8b9c0d",
            core=core,
            extensions=ext,
            signature="3045022100abc123..."
        )
        
        d = vac.to_dict()
        
        # Verify structure
        assert d["version"] == VAC_VERSION
        assert d["core"]["agent_id"] == "abc123def456"
        assert "extensions" in d
        assert "partner_attestations" in d["extensions"]
        assert d["extensions"]["partner_attestations"][0]["claims"]["legal_entity_id"] == "CORP-12345-DE"
        assert d["signature"] == "3045022100abc123..."
        
        print("  ✓ PASSED")
        tests_passed += 1
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 10: JSON serialization roundtrip
    print("\n[Test 10] JSON serialization roundtrip...")
    try:
        core = VACCore(
            agent_id="agent123",
            total_transactions=5,
            total_volume_sats=500000,
            unique_counterparties=3,
            rails_used=["lightning"]
        )
        vac = VACCredential(
            version=VAC_VERSION,
            issued_at="2026-03-23T16:00:00Z",
            expires_at="2026-03-30T16:00:00Z",
            credential_id="vac_agent123_abc123",
            core=core
        )
        
        # Serialize
        json_str = json.dumps(vac.to_dict())
        
        # Deserialize
        loaded = json.loads(json_str)
        
        # Verify
        assert loaded["version"] == VAC_VERSION
        assert loaded["core"]["agent_id"] == "agent123"
        
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
