#!/usr/bin/env python3
"""
Organization Registry Tests
Observer Protocol - Organizational Attestation Phase 1

Comprehensive tests for organization registration, queries, and lifecycle.
Run with: pytest test_organization_registry.py -v
"""

import pytest
import hashlib
import uuid
from datetime import datetime

# Import the modules to test
import sys
sys.path.insert(0, '/home/futurebit/.openclaw/workspace/observer-protocol-repo')

from organization_models import (
    OrganizationRegistrationRequest,
    OrganizationRevocationRequest
)
from organization_registry import (
    OrganizationRegistry,
    OrganizationAlreadyExistsError,
    OrganizationNotFoundError,
    OrganizationRevokedError,
    register_organization,
    get_organization,
    revoke_organization
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def registry():
    """Create a fresh OrganizationRegistry instance."""
    return OrganizationRegistry()


@pytest.fixture
def sample_org_data():
    """Sample organization data for testing."""
    # Generate unique keys for each test run
    unique_id = str(uuid.uuid4())[:8]
    
    return {
        "name": f"Test Corp {unique_id}",
        "domain": f"testcorp-{unique_id}.com",
        "display_name": f"Test Corporation {unique_id}",
        "description": "A test organization for unit tests",
        "master_public_key": "04" + "a1b2c3d4e5f6" * 10 + "a1b2",  # 66 chars for secp256k1 uncompressed
        "revocation_public_key": "04" + "f6e5d4c3b2a1" * 10 + "f6e5",  # Different key
        "key_type": "secp256k1",
        "contact_email": f"security@testcorp-{unique_id}.com",
        "metadata": {"test": True, "industry": "technology"}
    }


@pytest.fixture
def registered_org(registry, sample_org_data):
    """Create and return a registered organization."""
    result = registry.register_organization(**sample_org_data)
    return result


# ============================================================
# MODEL VALIDATION TESTS
# ============================================================

class TestOrganizationModels:
    """Test Pydantic model validation."""
    
    def test_valid_registration_request(self):
        """Test creating a valid registration request."""
        request = OrganizationRegistrationRequest(
            name="Acme Corp",
            domain="acme.com",
            master_public_key="04" + "a" * 128,
            revocation_public_key="04" + "b" * 128,
            key_type="secp256k1"
        )
        assert request.name == "Acme Corp"
        assert request.domain == "acme.com"
        
    def test_domain_normalization(self):
        """Test that domains are normalized to lowercase."""
        request = OrganizationRegistrationRequest(
            name="Acme Corp",
            domain="ACME.COM",
            master_public_key="04" + "a" * 128,
            revocation_public_key="04" + "b" * 128,
            key_type="secp256k1"
        )
        assert request.domain == "acme.com"
        
    def test_invalid_domain_format(self):
        """Test that invalid domains are rejected."""
        with pytest.raises(ValueError):
            OrganizationRegistrationRequest(
                name="Acme Corp",
                domain="not_a_valid_domain",
                master_public_key="04" + "a" * 128,
                revocation_public_key="04" + "b" * 128,
                key_type="secp256k1"
            )
            
    def test_same_master_and_revocation_keys(self):
        """Test that master and revocation keys must differ."""
        with pytest.raises(ValueError):
            OrganizationRegistrationRequest(
                name="Acme Corp",
                domain="acme.com",
                master_public_key="04" + "a" * 128,
                revocation_public_key="04" + "a" * 128,  # Same as master
                key_type="secp256k1"
            )
            
    def test_invalid_key_type(self):
        """Test that invalid key types are rejected."""
        with pytest.raises(ValueError):
            OrganizationRegistrationRequest(
                name="Acme Corp",
                domain="acme.com",
                master_public_key="04" + "a" * 128,
                revocation_public_key="04" + "b" * 128,
                key_type="invalid_key_type"
            )
            
    def test_display_name_defaults_to_name(self):
        """Test that display_name defaults to name if not provided."""
        request = OrganizationRegistrationRequest(
            name="Acme Corp",
            domain="acme.com",
            master_public_key="04" + "a" * 128,
            revocation_public_key="04" + "b" * 128,
            key_type="secp256k1"
        )
        assert request.display_name == "Acme Corp"


# ============================================================
# REGISTRY REGISTRATION TESTS
# ============================================================

class TestOrganizationRegistration:
    """Test organization registration functionality."""
    
    def test_successful_registration(self, registry, sample_org_data):
        """Test basic organization registration."""
        result = registry.register_organization(**sample_org_data)
        
        assert "org_id" in result
        assert result["name"] == sample_org_data["name"]
        assert result["domain"] == sample_org_data["domain"].lower()
        assert result["status"] == "active"
        assert result["verification_status"] == "self_attested"
        assert "master_public_key_hash" in result
        assert "revocation_public_key_hash" in result
        assert "registered_at" in result
        
    def test_duplicate_domain_rejected(self, registry, sample_org_data, registered_org):
        """Test that duplicate domains are rejected."""
        # Try to register with same domain
        duplicate_data = sample_org_data.copy()
        duplicate_data["name"] = "Different Name"
        duplicate_data["master_public_key"] = "04" + "c" * 128  # Different key
        duplicate_data["revocation_public_key"] = "04" + "d" * 128
        
        with pytest.raises(OrganizationAlreadyExistsError):
            registry.register_organization(**duplicate_data)
            
    def test_duplicate_master_key_rejected(self, registry, sample_org_data, registered_org):
        """Test that duplicate master keys are rejected."""
        # Try to register with same master key but different domain
        duplicate_data = sample_org_data.copy()
        duplicate_data["domain"] = "different-domain-12345.com"
        duplicate_data["revocation_public_key"] = "04" + "e" * 128  # Different revocation key
        
        with pytest.raises(OrganizationAlreadyExistsError):
            registry.register_organization(**duplicate_data)
            
    def test_same_keys_rejected(self, registry):
        """Test that master and revocation keys must be different."""
        data = {
            "name": "Test Corp",
            "domain": "testcorp-keys.com",
            "master_public_key": "04" + "a" * 128,
            "revocation_public_key": "04" + "a" * 128,  # Same key
            "key_type": "secp256k1"
        }
        
        with pytest.raises(ValueError) as exc_info:
            registry.register_organization(**data)
        assert "different" in str(exc_info.value).lower()
        
    def test_domain_validation(self, registry):
        """Test domain validation during registration."""
        invalid_domains = [
            "not_a_domain",
            "no-tld",
            ".com",
            "a.b",
            ""
        ]
        
        for domain in invalid_domains:
            data = {
                "name": "Test Corp",
                "domain": domain,
                "master_public_key": "04" + "a" * 128,
                "revocation_public_key": "04" + "b" * 128,
                "key_type": "secp256k1"
            }
            
            with pytest.raises((ValueError, Exception)):
                registry.register_organization(**data)
                
    def test_key_hash_computation(self, registry, sample_org_data):
        """Test that key hashes are computed correctly."""
        result = registry.register_organization(**sample_org_data)
        
        # Verify hash format (64 hex characters = 256 bits)
        assert len(result["master_public_key_hash"]) == 64
        assert len(result["revocation_public_key_hash"]) == 64
        assert all(c in "0123456789abcdef" for c in result["master_public_key_hash"])
        

# ============================================================
# REGISTRY QUERY TESTS
# ============================================================

class TestOrganizationQueries:
    """Test organization query functionality."""
    
    def test_get_organization_by_id(self, registry, registered_org):
        """Test retrieving organization by ID."""
        org_id = registered_org["org_id"]
        result = registry.get_organization(org_id)
        
        assert result["org_id"] == org_id
        assert result["name"] == registered_org["name"]
        assert result["domain"] == registered_org["domain"]
        assert "master_public_key_hash" in result
        # Should not include full keys by default
        assert "master_public_key" not in result
        
    def test_get_organization_with_keys(self, registry, registered_org):
        """Test retrieving organization with full public keys."""
        org_id = registered_org["org_id"]
        result = registry.get_organization(org_id, include_public_keys=True)
        
        assert "master_public_key" in result
        assert "revocation_public_key" in result
        
    def test_get_organization_not_found(self, registry):
        """Test retrieving non-existent organization."""
        fake_id = "550e8400-e29b-41d4-a716-446655440000"
        
        with pytest.raises(OrganizationNotFoundError):
            registry.get_organization(fake_id)
            
    def test_get_organization_by_domain(self, registry, registered_org):
        """Test retrieving organization by domain."""
        domain = registered_org["domain"]
        result = registry.get_organization_by_domain(domain)
        
        assert result["org_id"] == registered_org["org_id"]
        assert result["domain"] == domain
        
    def test_get_organization_by_domain_case_insensitive(self, registry, registered_org):
        """Test domain lookup is case insensitive."""
        domain = registered_org["domain"].upper()
        result = registry.get_organization_by_domain(domain)
        
        assert result["org_id"] == registered_org["org_id"]
        
    def test_get_organization_by_key_hash(self, registry, registered_org):
        """Test retrieving organization by key hash."""
        key_hash = registered_org["master_public_key_hash"]
        result = registry.get_organization_by_key_hash(key_hash)
        
        assert result["org_id"] == registered_org["org_id"]
        assert result["master_public_key_hash"] == key_hash
        
    def test_get_organization_by_revocation_key_hash(self, registry, sample_org_data):
        """Test retrieving organization by revocation key hash."""
        # Register first
        registered = registry.register_organization(**sample_org_data)
        
        # Lookup by revocation key hash
        key_hash = registered["revocation_public_key_hash"]
        result = registry.get_organization_by_key_hash(key_hash)
        
        assert result["org_id"] == registered["org_id"]
        

# ============================================================
# LISTING AND FILTERING TESTS
# ============================================================

class TestOrganizationListing:
    """Test organization listing and filtering."""
    
    def test_list_organizations_default_active(self, registry, registered_org):
        """Test that listing defaults to active organizations."""
        result = registry.list_organizations()
        
        assert "organizations" in result
        assert "count" in result
        assert "total" in result
        
        # Should include our registered org
        org_ids = [org["org_id"] for org in result["organizations"]]
        assert registered_org["org_id"] in org_ids
        
    def test_list_organizations_pagination(self, registry):
        """Test pagination in organization listing."""
        result = registry.list_organizations(limit=5, offset=0)
        
        assert result["limit"] == 5
        assert result["offset"] == 0
        assert len(result["organizations"]) <= 5
        
    def test_list_organizations_by_status(self, registry, registered_org):
        """Test filtering by status."""
        # Should find active
        result = registry.list_organizations(status='active')
        org_ids = [org["org_id"] for org in result["organizations"]]
        assert registered_org["org_id"] in org_ids
        
        # Should not find in revoked
        result = registry.list_organizations(status='revoked')
        org_ids = [org["org_id"] for org in result["organizations"]]
        assert registered_org["org_id"] not in org_ids
        
    def test_list_organizations_by_domain_filter(self, registry, registered_org):
        """Test filtering by domain substring."""
        domain_part = registered_org["domain"].split('.')[0]
        result = registry.list_organizations(domain_filter=domain_part)
        
        org_ids = [org["org_id"] for org in result["organizations"]]
        assert registered_org["org_id"] in org_ids
        
    def test_list_all_statuses(self, registry):
        """Test listing all organizations regardless of status."""
        result = registry.list_organizations(status='all')
        
        # Should return organizations from all statuses
        assert "organizations" in result
        

# ============================================================
# LIFECYCLE TESTS (REVOKE, SUSPEND, REACTIVATE)
# ============================================================

class TestOrganizationLifecycle:
    """Test organization lifecycle operations."""
    
    def test_revoke_organization(self, registry, registered_org):
        """Test revoking an organization."""
        org_id = registered_org["org_id"]
        
        result = registry.revoke_organization(
            org_id=org_id,
            reason="Key compromise - rotating to new keypair"
        )
        
        assert result["org_id"] == org_id
        assert result["status"] == "revoked"
        assert "revoked_at" in result
        
    def test_revoke_already_revoked(self, registry, registered_org):
        """Test that revoking an already revoked org fails."""
        org_id = registered_org["org_id"]
        
        # Revoke first time
        registry.revoke_organization(org_id, "First revocation")
        
        # Second revocation should fail
        with pytest.raises(OrganizationRevokedError):
            registry.revoke_organization(org_id, "Second revocation")
            
    def test_revoke_nonexistent_organization(self, registry):
        """Test revoking a non-existent organization."""
        fake_id = "550e8400-e29b-41d4-a716-446655440000"
        
        with pytest.raises(OrganizationNotFoundError):
            registry.revoke_organization(fake_id, "Test revocation")
            
    def test_suspend_organization(self, registry, registered_org):
        """Test suspending an organization."""
        org_id = registered_org["org_id"]
        
        result = registry.suspend_organization(org_id, "Temporary suspension for review")
        
        assert result["org_id"] == org_id
        assert result["status"] == "suspended"
        assert "suspended_at" in result
        
    def test_suspend_revoked_organization_fails(self, registry, registered_org):
        """Test that suspending a revoked organization fails."""
        org_id = registered_org["org_id"]
        
        # Revoke first
        registry.revoke_organization(org_id, "Test revocation")
        
        # Suspend should fail
        with pytest.raises(OrganizationNotFoundError):
            registry.suspend_organization(org_id, "Should fail")
            
    def test_reactivate_suspended_organization(self, registry, registered_org):
        """Test reactivating a suspended organization."""
        org_id = registered_org["org_id"]
        
        # Suspend first
        registry.suspend_organization(org_id, "Temporary suspension")
        
        # Reactivate
        result = registry.reactivate_organization(org_id)
        
        assert result["org_id"] == org_id
        assert result["status"] == "active"
        assert "reactivated_at" in result
        
    def test_reactivate_active_organization_fails(self, registry, registered_org):
        """Test that reactivating an already active organization fails."""
        org_id = registered_org["org_id"]
        
        with pytest.raises(OrganizationNotFoundError):
            registry.reactivate_organization(org_id)
            
    def test_reactivate_revoked_organization_fails(self, registry, registered_org):
        """Test that reactivating a revoked organization fails."""
        org_id = registered_org["org_id"]
        
        # Revoke first
        registry.revoke_organization(org_id, "Permanent revocation")
        
        # Reactivate should fail
        with pytest.raises(OrganizationRevokedError):
            registry.reactivate_organization(org_id)
            
    def test_is_organization_active(self, registry, registered_org):
        """Test the is_organization_active helper method."""
        org_id = registered_org["org_id"]
        
        # Should be active initially
        assert registry.is_organization_active(org_id) is True
        
        # After revocation, should be inactive
        registry.revoke_organization(org_id, "Test revocation")
        assert registry.is_organization_active(org_id) is False
        
    def test_is_organization_active_nonexistent(self, registry):
        """Test is_organization_active for non-existent org."""
        fake_id = "550e8400-e29b-41d4-a716-446655440000"
        assert registry.is_organization_active(fake_id) is False


# ============================================================
# CONVENIENCE FUNCTION TESTS
# ============================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""
    
    def test_register_organization_convenience(self, sample_org_data):
        """Test the register_organization convenience function."""
        # Need to modify domain to avoid conflicts
        sample_org_data["domain"] = f"convenience-{uuid.uuid4().hex[:8]}.com"
        sample_org_data["master_public_key"] = "04" + uuid.uuid4().hex * 4
        sample_org_data["revocation_public_key"] = "04" + uuid.uuid4().hex * 4
        
        result = register_organization(**sample_org_data)
        
        assert "org_id" in result
        assert result["status"] == "active"
        
    def test_get_organization_convenience(self, sample_org_data):
        """Test the get_organization convenience function."""
        # Register first
        sample_org_data["domain"] = f"get-convenience-{uuid.uuid4().hex[:8]}.com"
        sample_org_data["master_public_key"] = "04" + uuid.uuid4().hex * 4
        sample_org_data["revocation_public_key"] = "04" + uuid.uuid4().hex * 4
        
        registered = register_organization(**sample_org_data)
        org_id = registered["org_id"]
        
        # Get using convenience function
        result = get_organization(org_id)
        
        assert result["org_id"] == org_id
        assert result["name"] == sample_org_data["name"]
        
    def test_revoke_organization_convenience(self, sample_org_data):
        """Test the revoke_organization convenience function."""
        # Register first
        sample_org_data["domain"] = f"revoke-convenience-{uuid.uuid4().hex[:8]}.com"
        sample_org_data["master_public_key"] = "04" + uuid.uuid4().hex * 4
        sample_org_data["revocation_public_key"] = "04" + uuid.uuid4().hex * 4
        
        registered = register_organization(**sample_org_data)
        org_id = registered["org_id"]
        
        # Revoke using convenience function
        result = revoke_organization(org_id, "Test revocation via convenience function")
        
        assert result["org_id"] == org_id
        assert result["status"] == "revoked"


# ============================================================
# KEY VERIFICATION TESTS
# ============================================================

class TestKeyVerification:
    """Test key verification functionality."""
    
    def test_verify_key_ownership_stub(self, registry, registered_org):
        """Test the verify_key_ownership stub (always returns True in Phase 1)."""
        org_id = registered_org["org_id"]
        
        # In Phase 1, this always returns True (stub implementation)
        result = registry.verify_key_ownership(
            org_id=org_id,
            message="test message",
            signature="fake_signature",
            key_type="master"
        )
        
        assert result is True


# ============================================================
# EDGE CASE AND ERROR HANDLING TESTS
# ============================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_metadata(self, registry):
        """Test registration with empty metadata."""
        data = {
            "name": "Test Corp",
            "domain": f"empty-meta-{uuid.uuid4().hex[:8]}.com",
            "master_public_key": "04" + uuid.uuid4().hex * 4,
            "revocation_public_key": "04" + uuid.uuid4().hex * 4,
            "key_type": "secp256k1",
            "metadata": {}
        }
        
        result = registry.register_organization(**data)
        assert result["status"] == "active"
        
    def test_none_metadata(self, registry):
        """Test registration with None metadata."""
        data = {
            "name": "Test Corp",
            "domain": f"none-meta-{uuid.uuid4().hex[:8]}.com",
            "master_public_key": "04" + uuid.uuid4().hex * 4,
            "revocation_public_key": "04" + uuid.uuid4().hex * 4,
            "key_type": "secp256k1",
            "metadata": None
        }
        
        result = registry.register_organization(**data)
        assert result["status"] == "active"
        
    def test_unicode_in_name_and_description(self, registry):
        """Test registration with unicode characters."""
        data = {
            "name": "测试公司 🚀 Test Corp",
            "domain": f"unicode-{uuid.uuid4().hex[:8]}.com",
            "display_name": "Unicode Test 🎉",
            "description": "Testing unicode: 日本語 español français",
            "master_public_key": "04" + uuid.uuid4().hex * 4,
            "revocation_public_key": "04" + uuid.uuid4().hex * 4,
            "key_type": "secp256k1"
        }
        
        result = registry.register_organization(**data)
        assert result["name"] == data["name"]
        
    def test_very_long_description(self, registry):
        """Test registration with long description."""
        data = {
            "name": "Test Corp",
            "domain": f"long-desc-{uuid.uuid4().hex[:8]}.com",
            "description": "A" * 10000,  # Very long description
            "master_public_key": "04" + uuid.uuid4().hex * 4,
            "revocation_public_key": "04" + uuid.uuid4().hex * 4,
            "key_type": "secp256k1"
        }
        
        result = registry.register_organization(**data)
        assert result["status"] == "active"


# ============================================================
# INTEGRATION TESTS (if running with live database)
# ============================================================

@pytest.mark.integration
class TestIntegration:
    """
    Integration tests that require a live database.
    
    These tests are skipped by default. Run with:
    pytest test_organization_registry.py -m integration
    """
    
    def test_database_connection(self, registry):
        """Test that database connection works."""
        conn = registry._get_db_connection()
        assert conn is not None
        conn.close()
        
    def test_database_write_and_read(self, registry, sample_org_data):
        """Test writing to and reading from database."""
        # Write
        registered = registry.register_organization(**sample_org_data)
        org_id = registered["org_id"]
        
        # Read
        result = registry.get_organization(org_id)
        
        assert result["org_id"] == org_id
        assert result["name"] == sample_org_data["name"]


if __name__ == "__main__":
    # Run tests with pytest if available, otherwise print message
    try:
        import pytest
        print("Run tests with: pytest test_organization_registry.py -v")
    except ImportError:
        print("pytest not installed. Install with: pip install pytest")
        print("\nAlternatively, you can run manual tests:")
        
        # Simple manual test
        registry = OrganizationRegistry()
        
        # Try to list organizations
        try:
            orgs = registry.list_organizations(limit=5)
            print(f"\nFound {orgs['total']} organizations in registry")
            for org in orgs['organizations'][:3]:
                print(f"  - {org['name']} ({org['domain']}) - {org['status']}")
        except Exception as e:
            print(f"\nCould not list organizations: {e}")
            print("This is expected if the database is not configured.")
