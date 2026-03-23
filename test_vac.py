#!/usr/bin/env python3
"""
VAC (Verified Agent Credential) Test Suite
Observer Protocol VAC Specification v0.3

Run with: python -m pytest test_vac.py -v
"""

import pytest
import json
import hashlib
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
sys.path.insert(0, '/home/futurebit/.openclaw/workspace/observer-protocol')

from vac_generator import (
    VACCore,
    PartnerAttestation,
    CounterpartyMetadata,
    VACExtensions,
    VACCredential,
    VACGenerator,
    VAC_VERSION,
    VAC_MAX_AGE_DAYS
)
from partner_registry import PartnerRegistry


class TestVACCore:
    """Test VACCore dataclass."""
    
    def test_basic_creation(self):
        core = VACCore(
            agent_id="test_agent_123",
            total_transactions=10,
            total_volume_sats=1000000,
            unique_counterparties=5,
            rails_used=["lightning", "L402"]
        )
        assert core.agent_id == "test_agent_123"
        assert core.total_transactions == 10
        assert core.total_volume_sats == 1000000
    
    def test_to_dict_omits_none(self):
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
    
    def test_to_dict_includes_optional_when_set(self):
        core = VACCore(
            agent_id="test_agent_123",
            total_transactions=10,
            total_volume_sats=1000000,
            unique_counterparties=5,
            rails_used=["lightning"],
            first_transaction_at="2026-01-01T00:00:00Z",
            last_transaction_at="2026-03-01T00:00:00Z"
        )
        d = core.to_dict()
        assert d["first_transaction_at"] == "2026-01-01T00:00:00Z"
        assert d["last_transaction_at"] == "2026-03-01T00:00:00Z"


class TestPartnerAttestation:
    """Test PartnerAttestation dataclass."""
    
    def test_basic_creation(self):
        att = PartnerAttestation(
            partner_id="partner-123",
            partner_name="Test Partner",
            partner_type="corpo",
            claims={"legal_entity_id": "CORP-123"},
            issued_at="2026-03-23T16:00:00Z"
        )
        assert att.partner_type == "corpo"
        assert att.claims["legal_entity_id"] == "CORP-123"
    
    def test_to_dict_omits_expires_when_none(self):
        att = PartnerAttestation(
            partner_id="partner-123",
            partner_name="Test Partner",
            partner_type="corpo",
            claims={},
            issued_at="2026-03-23T16:00:00Z"
        )
        d = att.to_dict()
        assert "expires_at" not in d


class TestVACExtensions:
    """Test VACExtensions dataclass."""
    
    def test_empty_returns_none(self):
        ext = VACExtensions()
        assert ext.to_dict() is None
    
    def test_with_attestations(self):
        att = PartnerAttestation(
            partner_id="p1",
            partner_name="Corpo",
            partner_type="corpo",
            claims={"legal_entity_id": "CORP-123"},
            issued_at="2026-03-23T16:00:00Z"
        )
        ext = VACExtensions(partner_attestations=[att])
        d = ext.to_dict()
        assert d is not None
        assert "partner_attestations" in d
        assert len(d["partner_attestations"]) == 1


class TestVACCredential:
    """Test VACCredential dataclass."""
    
    def test_basic_creation(self):
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
        assert vac.version == VAC_VERSION
        assert vac.core.agent_id == "agent123"
    
    def test_canonical_json_sorts_keys(self):
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
    
    def test_compute_hash_deterministic(self):
        core = VACCore(
            agent_id="agent123",
            total_transactions=5,
            total_volume_sats=500000,
            unique_counterparties=3,
            rails_used=["lightning"]
        )
        vac1 = VACCredential(
            version=VAC_VERSION,
            issued_at="2026-03-23T16:00:00Z",
            expires_at="2026-03-30T16:00:00Z",
            credential_id="vac_agent123_abc123",
            core=core
        )
        vac2 = VACCredential(
            version=VAC_VERSION,
            issued_at="2026-03-23T16:00:00Z",
            expires_at="2026-03-30T16:00:00Z",
            credential_id="vac_agent123_abc123",
            core=core
        )
        assert vac1.compute_hash() == vac2.compute_hash()
    
    def test_optional_fields_omitted(self):
        """CRITICAL: Optional fields must be omitted, not null."""
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
            # No extensions, no signature
        )
        d = vac.to_dict()
        assert "extensions" not in d
        assert "signature" not in d


class TestVACGenerator:
    """Test VACGenerator class."""
    
    @patch.dict('os.environ', {'OP_SIGNING_KEY': 'a'*64})
    @patch('vac_generator.psycopg2.connect')
    def test_aggregate_core_fields(self, mock_connect):
        # Setup mock
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {'total_transactions': 10, 'total_volume_sats': 1000000, 'unique_counterparties': 5},
            {'first_transaction': datetime(2026, 1, 1), 'last_transaction': datetime(2026, 3, 1)}
        ]
        mock_cursor.fetchall.return_value = [
            {'protocol': 'lightning'},
            {'protocol': 'L402'}
        ]
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        generator = VACGenerator()
        core = generator._aggregate_core_fields("agent123")
        
        assert core.total_transactions == 10
        assert core.total_volume_sats == 1000000
        assert "lightning" in core.rails_used
        assert "L402" in core.rails_used


class TestPartnerRegistry:
    """Test PartnerRegistry class."""
    
    @patch('partner_registry.psycopg2.connect')
    def test_register_partner(self, mock_connect):
        # Setup mock
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'partner_id': '550e8400-e29b-41d4-a716-446655440000',
            'partner_name': 'Test Partner',
            'partner_type': 'corpo',
            'registered_at': datetime(2026, 3, 23, 16, 0, 0)
        }
        
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        registry = PartnerRegistry()
        result = registry.register_partner(
            partner_name="Test Partner",
            partner_type="corpo",
            public_key="pubkey123"
        )
        
        assert result['partner_name'] == "Test Partner"
        assert result['partner_type'] == "corpo"
        assert result['status'] == "registered"


class TestCorpoMigration:
    """Test Corpo legal_entity_id migration."""
    
    def test_legal_entity_id_location(self):
        """Verify legal_entity_id is in partner_attestations.corpo.claims."""
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
        assert "corpo" == att.partner_type
        assert "legal_entity_id" in d["partner_attestations"][0]["claims"]
        assert d["partner_attestations"][0]["claims"]["legal_entity_id"] == "CORP-12345-DE"


class TestVACSchemaConstraints:
    """Test VAC schema constraints per v0.3 spec."""
    
    def test_no_null_values_in_output(self):
        """CRITICAL: Optional fields are OMITTED ENTIRELY, not null."""
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
        
        # Should not contain any null values
        assert 'null' not in json_str
    
    def test_version_format(self):
        """Version must be semantic version format."""
        assert VAC_VERSION.count('.') == 2
        parts = VAC_VERSION.split('.')
        assert all(p.isdigit() for p in parts)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
