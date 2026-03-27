#!/usr/bin/env python3
"""
Organization Registry API Endpoints
Observer Protocol - Organizational Attestation Phase 1

FastAPI endpoints for organization registration and management.
These endpoints follow the existing patterns in api-server-v2.py.
"""

from fastapi import FastAPI, HTTPException, Query, APIRouter
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime
import sys

# Import organization models and registry
import os
# Use environment variable for repo path, with sensible default
OP_REPO_PATH = os.environ.get('OP_REPO_PATH', os.path.expanduser('~/.openclaw/workspace/observer-protocol-repo'))
sys.path.insert(0, OP_REPO_PATH)
from organization_models import (
    OrganizationRegistrationRequest,
    OrganizationResponse,
    OrganizationDetailResponse,
    OrganizationRevocationRequest,
    OrganizationRevocationResponse,
    OrganizationListResponse,
    OrganizationQueryParams
)
from organization_registry import (
    OrganizationRegistry,
    OrganizationAlreadyExistsError,
    OrganizationNotFoundError,
    OrganizationRevokedError
)

# Create router (can be included in main FastAPI app)
org_router = APIRouter(prefix="/observer", tags=["organizations"])

# Initialize registry
registry = OrganizationRegistry()


@org_router.post("/register-org", response_model=dict, status_code=201)
def register_organization(request: OrganizationRegistrationRequest):
    """
    Register a new organization in the Observer Protocol registry.
    
    Organizations are credential issuers (not agents) that can:
    - Issue attestations that agents include in their VAC credentials
    - Sign credentials on behalf of their domain/brand
    - Revoke their own credentials if compromised
    
    **Key Design Principles:**
    - Organizations are credential issuers, not agents
    - OP does NOT verify real-world identity — just anchors the cryptographic attestation
    - Separate revocation keypair from master keypair
    - Self-attested at this stage (no KYB integration in Phase 1)
    
    **Required Fields:**
    - `name`: Organization name
    - `domain`: Organization domain (e.g., "acme.com")
    - `master_public_key`: Public key for signing attestations
    - `revocation_public_key`: Separate key for revocation operations
    - `key_type`: "secp256k1" or "ed25519"
    
    **Returns:**
    - `org_id`: Unique organization identifier (UUID)
    - `master_public_key_hash`: SHA256 hash of master key (for lookups)
    - `revocation_public_key_hash`: SHA256 hash of revocation key
    - `status`: "active"
    - `verification_status`: "self_attested" (Phase 1)
    """
    try:
        result = registry.register_organization(
            name=request.name,
            domain=request.domain,
            master_public_key=request.master_public_key,
            revocation_public_key=request.revocation_public_key,
            key_type=request.key_type,
            display_name=request.display_name,
            description=request.description,
            contact_email=request.contact_email,
            metadata=request.metadata or {}
        )
        return result
        
    except OrganizationAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Organization registration failed: {str(e)}")


@org_router.get("/orgs/{org_id}", response_model=dict)
def get_organization(
    org_id: str,
    include_keys: bool = Query(False, description="Include full public keys in response")
):
    """
    Get organization details by ID.
    
    **Path Parameters:**
    - `org_id`: Organization UUID
    
    **Query Parameters:**
    - `include_keys`: If true, includes full public keys (default: false, returns only hashes)
    
    **Returns:**
    - Organization profile
    - Key hashes for verification
    - Status and verification level
    - Registration metadata
    """
    try:
        result = registry.get_organization(org_id, include_public_keys=include_keys)
        return result
        
    except OrganizationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve organization: {str(e)}")


@org_router.get("/orgs/by-domain/{domain}", response_model=dict)
def get_organization_by_domain(domain: str):
    """
    Get organization by domain.
    
    **Path Parameters:**
    - `domain`: Organization domain (e.g., "acme.com")
    
    **Returns:**
    - Organization details (same as `/orgs/{org_id}`)
    
    This endpoint enables lookup of organizations by their domain,
    which is useful for domain-based verification workflows.
    """
    try:
        result = registry.get_organization_by_domain(domain)
        return result
        
    except OrganizationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve organization: {str(e)}")


@org_router.get("/orgs/by-key/{key_hash}", response_model=dict)
def get_organization_by_key_hash(key_hash: str):
    """
    Get organization by public key hash.
    
    **Path Parameters:**
    - `key_hash`: SHA256 hash of organization's public key (master or revocation)
    
    **Returns:**
    - Organization details (same as `/orgs/{org_id}`)
    
    This endpoint enables cryptographic verification workflows where
    you have a public key and need to find the associated organization.
    """
    try:
        result = registry.get_organization_by_key_hash(key_hash)
        return result
        
    except OrganizationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve organization: {str(e)}")


@org_router.get("/orgs", response_model=dict)
def list_organizations(
    status: Optional[str] = Query('active', description="Filter by status: active, suspended, revoked, all"),
    verification_status: Optional[str] = Query(None, description="Filter by verification: self_attested, pending_kyb, kyb_verified, kyb_failed, all"),
    domain: Optional[str] = Query(None, description="Filter by domain (partial match)"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """
    List organizations with optional filtering.
    
    **Query Parameters:**
    - `status`: Filter by status (default: "active")
    - `verification_status`: Filter by verification level
    - `domain`: Filter by domain (partial match)
    - `limit`: Maximum results (default: 50, max: 100)
    - `offset`: Pagination offset (default: 0)
    
    **Returns:**
    - List of organizations
    - Total count
    - Pagination info
    """
    try:
        result = registry.list_organizations(
            status=status,
            verification_status=verification_status,
            domain_filter=domain,
            limit=limit,
            offset=offset
        )
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list organizations: {str(e)}")


@org_router.post("/orgs/{org_id}/revoke", response_model=dict)
def revoke_organization(
    org_id: str,
    request: OrganizationRevocationRequest
):
    """
    Revoke an organization (soft delete).
    
    **Path Parameters:**
    - `org_id`: Organization UUID to revoke
    
    **Request Body:**
    - `reason`: Reason for revocation (required, min 10 chars)
    - `revocation_signature`: Optional signature from revocation keypair (Phase 2+ will require this)
    
    **Effects:**
    - Organization status changes to "revoked"
    - All credentials issued by this org should be considered invalid
    - Cannot be undone (unlike suspension)
    
    **Returns:**
    - Revocation confirmation
    - Timestamp of revocation
    
    **Note:** In Phase 1, cryptographic proof of revocation key ownership is optional.
    Future phases will require a valid signature from the revocation keypair.
    """
    try:
        result = registry.revoke_organization(
            org_id=org_id,
            reason=request.reason,
            revocation_signature=request.revocation_signature
        )
        return result
        
    except OrganizationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OrganizationRevokedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Revocation failed: {str(e)}")


@org_router.post("/orgs/{org_id}/suspend", response_model=dict)
def suspend_organization(
    org_id: str,
    reason: str = Query(..., min_length=10, description="Reason for suspension")
):
    """
    Suspend an organization (temporary deactivation).
    
    **Path Parameters:**
    - `org_id`: Organization UUID to suspend
    
    **Query Parameters:**
    - `reason`: Reason for suspension (required, min 10 chars)
    
    **Effects:**
    - Organization status changes to "suspended"
    - Credentials are temporarily invalid
    - Can be reactivated (unlike revocation)
    
    **Returns:**
    - Suspension confirmation
    - Timestamp of suspension
    """
    try:
        result = registry.suspend_organization(org_id, reason)
        return result
        
    except OrganizationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suspension failed: {str(e)}")


@org_router.post("/orgs/{org_id}/reactivate", response_model=dict)
def reactivate_organization(org_id: str):
    """
    Reactivate a suspended organization.
    
    **Path Parameters:**
    - `org_id`: Organization UUID to reactivate
    
    **Effects:**
    - Organization status changes back to "active"
    - Credentials become valid again
    
    **Returns:**
    - Reactivation confirmation
    - Timestamp of reactivation
    
    **Note:** Cannot reactivate a revoked organization. Revocation is permanent.
    """
    try:
        result = registry.reactivate_organization(org_id)
        return result
        
    except OrganizationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OrganizationRevokedError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reactivation failed: {str(e)}")


@org_router.get("/orgs/{org_id}/verify-key")
def verify_organization_key(
    org_id: str,
    key_hash: str = Query(..., description="SHA256 hash of public key to verify"),
    key_type: str = Query('master', description="Key type: 'master' or 'revocation'")
):
    """
    Verify that a key hash belongs to an organization.
    
    **Path Parameters:**
    - `org_id`: Organization UUID
    
    **Query Parameters:**
    - `key_hash`: SHA256 hash of public key to verify
    - `key_type`: Which key to check ('master' or 'revocation')
    
    **Returns:**
    - `valid`: Boolean indicating if key hash matches
    - `org_id`: Organization ID
    - `key_type`: The key type that matched (if valid)
    
    This endpoint is useful for cryptographic verification workflows
    where you need to confirm a public key belongs to a specific organization.
    """
    try:
        org = registry.get_organization(org_id)
        
        # Normalize key hash
        key_hash = key_hash.lower().replace('0x', '')
        
        # Check against stored hashes
        master_match = key_hash == org.get('master_public_key_hash', '').lower().replace('0x', '')
        revocation_match = key_hash == org.get('revocation_public_key_hash', '').lower().replace('0x', '')
        
        if key_type == 'master' and master_match:
            return {
                "valid": True,
                "org_id": org_id,
                "key_type": "master",
                "message": "Key hash matches organization's master key"
            }
        elif key_type == 'revocation' and revocation_match:
            return {
                "valid": True,
                "org_id": org_id,
                "key_type": "revocation",
                "message": "Key hash matches organization's revocation key"
            }
        elif master_match:
            return {
                "valid": True,
                "org_id": org_id,
                "key_type": "master",
                "requested_type": key_type,
                "message": f"Key hash matches master key (you requested {key_type})"
            }
        elif revocation_match:
            return {
                "valid": True,
                "org_id": org_id,
                "key_type": "revocation",
                "requested_type": key_type,
                "message": f"Key hash matches revocation key (you requested {key_type})"
            }
        else:
            return {
                "valid": False,
                "org_id": org_id,
                "requested_type": key_type,
                "message": "Key hash does not match any organization key"
            }
            
    except OrganizationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Key verification failed: {str(e)}")


# ============================================================
# UTILITY ENDPOINTS
# ============================================================

@org_router.get("/orgs/health/check")
def organizations_health_check():
    """
    Health check for organization registry.
    
    Returns basic stats about the registry:
    - Total organizations
    - Active organizations
    - Self-attested vs KYB verified counts
    """
    try:
        all_orgs = registry.list_organizations(status='all', limit=10000)
        active_orgs = registry.list_organizations(status='active', limit=10000)
        
        # Count by verification status
        self_attested = registry.list_organizations(
            status='all', 
            verification_status='self_attested', 
            limit=10000
        )
        
        return {
            "status": "healthy",
            "total_organizations": all_orgs['total'],
            "active_organizations": active_orgs['total'],
            "self_attested": self_attested['total'],
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


# ============================================================
# INTEGRATION WITH MAIN API
# ============================================================

"""
To integrate these endpoints into the main API server (api-server-v2.py),
add the following line after creating the FastAPI app:

    app.include_router(org_router)

Or with the existing prefix:

    app.include_router(org_router, prefix="/observer")

The router already has the prefix set, so use:

    app.include_router(org_router)
"""

if __name__ == "__main__":
    # For testing the router directly
    from fastapi import FastAPI
    import uvicorn
    
    app = FastAPI(
        title="Observer Protocol - Organization Registry",
        description="API for registering and managing organizations in Observer Protocol",
        version="1.0.0"
    )
    app.include_router(org_router)
    
    print("Starting Organization Registry API...")
    print("Endpoints:")
    print("  POST /observer/register-org")
    print("  GET  /observer/orgs/{org_id}")
    print("  GET  /observer/orgs/by-domain/{domain}")
    print("  GET  /observer/orgs/by-key/{key_hash}")
    print("  GET  /observer/orgs")
    print("  POST /observer/orgs/{org_id}/revoke")
    print("  POST /observer/orgs/{org_id}/suspend")
    print("  POST /observer/orgs/{org_id}/reactivate")
    print("  GET  /observer/orgs/{org_id}/verify-key")
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
