#!/usr/bin/env python3
"""
Organization Models - Observer Protocol
Organizational Attestation Phase 1

Pydantic models for organization registration and management.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from datetime import datetime


class OrganizationBase(BaseModel):
    """Base organization model with common fields."""
    name: str = Field(..., min_length=1, max_length=200, description="Organization name")
    domain: str = Field(..., min_length=4, max_length=255, description="Organization domain (e.g., example.com)")
    display_name: Optional[str] = Field(None, max_length=200, description="Display name (defaults to name if not provided)")
    description: Optional[str] = Field(None, max_length=2000, description="Organization description")
    
    @validator('domain')
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate domain format and normalize to lowercase."""
        v = v.lower().strip()
        # Basic domain validation - at least one dot, valid characters
        if '.' not in v or len(v) < 4:
            raise ValueError('Invalid domain format')
        # Check for valid domain characters
        import re
        if not re.match(r'^[a-z0-9][a-z0-9-]*\.[a-z]{2,}$', v):
            raise ValueError('Domain must be a valid format (e.g., example.com)')
        return v
    
    @validator('display_name', always=True)
    @classmethod
    def set_display_name(cls, v, values):
        """Set display_name to name if not provided."""
        if v is None or (isinstance(v, str) and v.strip() == ''):
            return values.get('name', '')
        return v


class OrganizationKeypair(BaseModel):
    """Organization keypair model."""
    master_public_key: str = Field(..., min_length=32, max_length=500, description="Master public key for signing attestations")
    revocation_public_key: str = Field(..., min_length=32, max_length=500, description="Revocation public key (separate from master for security)")
    key_type: Literal['secp256k1', 'ed25519'] = Field(..., description="Cryptographic key type")
    
    @validator('master_public_key', 'revocation_public_key')
    @classmethod
    def validate_public_key(cls, v: str) -> str:
        """Validate that public key is hex-encoded."""
        # Remove 0x prefix if present
        if v.startswith('0x'):
            v = v[2:]
        # Check if valid hex
        try:
            bytes.fromhex(v)
        except ValueError:
            raise ValueError('Public key must be hex-encoded')
        return v
    
    @validator('revocation_public_key')
    @classmethod
    def keys_must_differ(cls, v, values):
        """Ensure revocation key is different from master key."""
        master = values.get('master_public_key', '')
        # Normalize for comparison
        v_norm = v.lower().replace('0x', '')
        master_norm = master.lower().replace('0x', '')
        if v_norm == master_norm:
            raise ValueError('Revocation public key must be different from master public key')
        return v


class OrganizationRegistrationRequest(OrganizationBase, OrganizationKeypair):
    """
    Request body for registering a new organization.
    
    Organizations are credential issuers, not agents. They can issue attestations
    that agents include in their VAC credentials.
    """
    contact_email: Optional[str] = Field(None, max_length=255, description="Optional contact email for future KYB")
    metadata: Optional[dict] = Field(default_factory=dict, description="Additional metadata (JSON object)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Acme Corporation",
                "domain": "acme.com",
                "display_name": "Acme Corp",
                "description": "Enterprise software solutions",
                "master_public_key": "04a1b2c3d4e5f6...",
                "revocation_public_key": "04f6e5d4c3b2a1...",
                "key_type": "secp256k1",
                "contact_email": "security@acme.com",
                "metadata": {"industry": "technology", "founded": "2020"}
            }
        }


class OrganizationResponse(BaseModel):
    """Response model for organization queries."""
    org_id: str = Field(..., description="Unique organization identifier (UUID)")
    name: str = Field(..., description="Organization name")
    domain: str = Field(..., description="Organization domain")
    display_name: str = Field(..., description="Display name")
    description: Optional[str] = Field(None, description="Organization description")
    master_public_key_hash: str = Field(..., description="SHA256 hash of master public key")
    revocation_public_key_hash: str = Field(..., description="SHA256 hash of revocation public key")
    key_type: Literal['secp256k1', 'ed25519'] = Field(..., description="Cryptographic key type")
    status: Literal['active', 'suspended', 'revoked'] = Field(..., description="Organization status")
    verification_status: Literal['self_attested', 'pending_kyb', 'kyb_verified', 'kyb_failed'] = Field(..., description="Verification level")
    registered_at: datetime = Field(..., description="Registration timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "org_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Acme Corporation",
                "domain": "acme.com",
                "display_name": "Acme Corp",
                "description": "Enterprise software solutions",
                "master_public_key_hash": "a1b2c3d4e5f6...",
                "revocation_public_key_hash": "f6e5d4c3b2a1...",
                "key_type": "secp256k1",
                "status": "active",
                "verification_status": "self_attested",
                "registered_at": "2026-03-24T10:00:00Z",
                "updated_at": "2026-03-24T10:00:00Z",
                "metadata": {"industry": "technology"}
            }
        }


class OrganizationDetailResponse(OrganizationResponse):
    """Detailed response including public keys (for authorized access)."""
    master_public_key: str = Field(..., description="Master public key (for verification)")
    revocation_public_key: str = Field(..., description="Revocation public key")
    
    class Config:
        from_attributes = True


class OrganizationRevocationRequest(BaseModel):
    """Request body for revoking an organization."""
    reason: str = Field(..., min_length=10, max_length=1000, description="Reason for revocation")
    revocation_signature: Optional[str] = Field(None, description="Signature from revocation keypair proving authority (optional in Phase 1)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "reason": "Organization key compromise - rotating to new keypair",
                "revocation_signature": "3045022100..."
            }
        }


class OrganizationRevocationResponse(BaseModel):
    """Response model for organization revocation."""
    org_id: str = Field(..., description="Organization ID")
    status: Literal['revoked'] = Field(..., description="New status")
    revoked_at: datetime = Field(..., description="Revocation timestamp")
    reason: str = Field(..., description="Revocation reason")
    message: str = Field(..., description="Human-readable message")


class OrganizationListResponse(BaseModel):
    """Response model for listing organizations."""
    organizations: list[OrganizationResponse] = Field(..., description="List of organizations")
    count: int = Field(..., description="Total count")
    
    
class OrganizationQueryParams(BaseModel):
    """Query parameters for listing/filtering organizations."""
    status: Optional[Literal['active', 'suspended', 'revoked', 'all']] = Field('active', description="Filter by status")
    verification_status: Optional[Literal['self_attested', 'pending_kyb', 'kyb_verified', 'kyb_failed', 'all']] = Field(None, description="Filter by verification status")
    domain: Optional[str] = Field(None, description="Filter by domain (partial match)")
    limit: int = Field(50, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(0, ge=0, description="Offset for pagination")
