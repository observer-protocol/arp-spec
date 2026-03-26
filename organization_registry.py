#!/usr/bin/env python3
"""
Organization Registry Module
Observer Protocol - Organizational Attestation Phase 1

Manages organization registration, key storage, and lifecycle.
Organizations are credential issuers, not agents.
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import psycopg2
import psycopg2.extras

# Database connection URL (matches existing patterns)
DB_URL = "postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db"


class OrganizationRegistryError(Exception):
    """Base exception for organization registry errors."""
    pass


class OrganizationAlreadyExistsError(OrganizationRegistryError):
    """Raised when attempting to register an organization with duplicate domain or keys."""
    pass


class OrganizationNotFoundError(OrganizationRegistryError):
    """Raised when an organization is not found."""
    pass


class OrganizationRevokedError(OrganizationRegistryError):
    """Raised when attempting to use a revoked organization."""
    pass


class OrganizationRegistry:
    """
    Manages the organization registry for Observer Protocol.
    
    Organizations are credential issuers (not agents) that can:
    - Issue attestations that agents include in VAC credentials
    - Sign credentials on behalf of their domain/brand
    - Revoke their own credentials if compromised
    
    Key Design Principles:
    1. Organizations are credential issuers, not agents
    2. OP does NOT verify real-world identity — just anchors the cryptographic attestation
    3. Separate revocation keypair from master keypair
    4. Registry entries must be queryable by org_id, domain, and public key hash
    """
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
    
    def _get_db_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.db_url)
    
    def _compute_public_key_hash(self, public_key: str) -> str:
        """
        Compute SHA256 hash of public key.
        
        This is the canonical identifier for looking up organizations by key.
        """
        # Normalize: remove 0x prefix, lowercase
        normalized = public_key.lower().replace('0x', '')
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def _validate_domain(self, domain: str) -> str:
        """
        Validate and normalize domain.
        
        Returns normalized lowercase domain or raises ValueError.
        """
        domain = domain.lower().strip()
        
        # Basic domain validation
        if '.' not in domain or len(domain) < 4:
            raise ValueError(f"Invalid domain format: {domain}")
        
        # More strict validation
        pattern = r'^[a-z0-9][a-z0-9-]*\.[a-z]{2,}$'
        if not re.match(pattern, domain):
            raise ValueError(f"Domain must be a valid format (e.g., example.com): {domain}")
        
        return domain
    
    def register_organization(
        self,
        name: str,
        domain: str,
        master_public_key: str,
        revocation_public_key: str,
        key_type: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        contact_email: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Register a new organization in the registry.
        
        Args:
            name: Organization name
            domain: Organization domain (must be unique)
            master_public_key: Master public key for signing attestations
            revocation_public_key: Separate revocation keypair
            key_type: 'secp256k1' or 'ed25519'
            display_name: Optional display name (defaults to name)
            description: Optional organization description
            contact_email: Optional contact email for future KYB
            metadata: Optional metadata dictionary
            
        Returns:
            Dict with org_id and registration details
            
        Raises:
            OrganizationAlreadyExistsError: If domain or key hash already exists
            ValueError: If validation fails
        """
        # Validate domain
        domain = self._validate_domain(domain)
        
        # Normalize public keys
        master_public_key = master_public_key.lower().replace('0x', '')
        revocation_public_key = revocation_public_key.lower().replace('0x', '')
        
        # Validate keys are different
        if master_public_key == revocation_public_key:
            raise ValueError("Master and revocation public keys must be different")
        
        # Compute key hashes
        master_key_hash = self._compute_public_key_hash(master_public_key)
        revocation_key_hash = self._compute_public_key_hash(revocation_public_key)
        
        # Set default display_name
        if not display_name:
            display_name = name
        
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                INSERT INTO organizations (
                    name, domain, display_name, description,
                    master_public_key, master_public_key_hash,
                    revocation_public_key, revocation_public_key_hash,
                    key_type, contact_email, metadata,
                    status, verification_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', 'self_attested')
                RETURNING org_id, name, domain, registered_at
            """, (
                name, domain, display_name, description,
                master_public_key, master_key_hash,
                revocation_public_key, revocation_key_hash,
                key_type, contact_email, json.dumps(metadata or {})
            ))
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "org_id": str(result['org_id']),
                "name": result['name'],
                "domain": result['domain'],
                "master_public_key_hash": master_key_hash,
                "revocation_public_key_hash": revocation_key_hash,
                "key_type": key_type,
                "status": "active",
                "verification_status": "self_attested",
                "registered_at": result['registered_at'].isoformat(),
                "message": "Organization registered successfully. Note: This is a self-attested registration. OP does not verify real-world identity at this stage."
            }
            
        except psycopg2.IntegrityError as e:
            conn.rollback()
            error_msg = str(e).lower()
            if 'domain' in error_msg:
                raise OrganizationAlreadyExistsError(f"Organization with domain '{domain}' already exists")
            elif 'master_public_key_hash' in error_msg:
                raise OrganizationAlreadyExistsError("Organization with this master public key already exists")
            elif 'revocation_public_key_hash' in error_msg:
                raise OrganizationAlreadyExistsError("Organization with this revocation public key already exists")
            else:
                raise OrganizationAlreadyExistsError(f"Organization already exists: {e}")
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
    
    def get_organization(self, org_id: str, include_public_keys: bool = False) -> Dict[str, Any]:
        """
        Get organization by ID.
        
        Args:
            org_id: Organization UUID
            include_public_keys: If True, include full public keys in response
            
        Returns:
            Organization details dict
            
        Raises:
            OrganizationNotFoundError: If organization not found
        """
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            if include_public_keys:
                cursor.execute("""
                    SELECT org_id, name, domain, display_name, description,
                           master_public_key, master_public_key_hash,
                           revocation_public_key, revocation_public_key_hash,
                           key_type, status, verification_status,
                           registered_at, updated_at, revoked_at, metadata
                    FROM organizations
                    WHERE org_id = %s
                """, (org_id,))
            else:
                cursor.execute("""
                    SELECT org_id, name, domain, display_name, description,
                           master_public_key_hash, revocation_public_key_hash,
                           key_type, status, verification_status,
                           registered_at, updated_at, revoked_at, metadata
                    FROM organizations
                    WHERE org_id = %s
                """, (org_id,))
            
            row = cursor.fetchone()
            if not row:
                raise OrganizationNotFoundError(f"Organization with ID '{org_id}' not found")
            
            result = dict(row)
            result['org_id'] = str(result['org_id'])
            
            # Convert datetime fields to ISO format
            for key in ['registered_at', 'updated_at', 'revoked_at']:
                if result.get(key):
                    result[key] = result[key].isoformat()
            
            # Parse metadata JSON
            if result.get('metadata'):
                if isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
            else:
                result['metadata'] = {}
            
            return result
            
        finally:
            cursor.close()
            conn.close()
    
    def get_organization_by_domain(self, domain: str) -> Dict[str, Any]:
        """
        Get organization by domain.
        
        Args:
            domain: Organization domain
            
        Returns:
            Organization details dict
            
        Raises:
            OrganizationNotFoundError: If organization not found
        """
        domain = self._validate_domain(domain)
        
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT org_id, name, domain, display_name, description,
                       master_public_key_hash, revocation_public_key_hash,
                       key_type, status, verification_status,
                       registered_at, updated_at, revoked_at, metadata
                FROM organizations
                WHERE domain = %s
            """, (domain,))
            
            row = cursor.fetchone()
            if not row:
                raise OrganizationNotFoundError(f"Organization with domain '{domain}' not found")
            
            result = dict(row)
            result['org_id'] = str(result['org_id'])
            
            # Convert datetime fields
            for key in ['registered_at', 'updated_at', 'revoked_at']:
                if result.get(key):
                    result[key] = result[key].isoformat()
            
            # Parse metadata JSON
            if result.get('metadata'):
                if isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
            else:
                result['metadata'] = {}
            
            return result
            
        finally:
            cursor.close()
            conn.close()
    
    def get_organization_by_key_hash(self, key_hash: str) -> Dict[str, Any]:
        """
        Get organization by public key hash (master or revocation).
        
        Args:
            key_hash: SHA256 hash of public key
            
        Returns:
            Organization details dict
            
        Raises:
            OrganizationNotFoundError: If organization not found
        """
        # Normalize key hash
        key_hash = key_hash.lower().replace('0x', '')
        
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT org_id, name, domain, display_name, description,
                       master_public_key_hash, revocation_public_key_hash,
                       key_type, status, verification_status,
                       registered_at, updated_at, revoked_at, metadata
                FROM organizations
                WHERE master_public_key_hash = %s OR revocation_public_key_hash = %s
            """, (key_hash, key_hash))
            
            row = cursor.fetchone()
            if not row:
                raise OrganizationNotFoundError(f"Organization with key hash '{key_hash}' not found")
            
            result = dict(row)
            result['org_id'] = str(result['org_id'])
            
            # Convert datetime fields
            for key in ['registered_at', 'updated_at', 'revoked_at']:
                if result.get(key):
                    result[key] = result[key].isoformat()
            
            # Parse metadata JSON
            if result.get('metadata'):
                if isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
            else:
                result['metadata'] = {}
            
            return result
            
        finally:
            cursor.close()
            conn.close()
    
    def list_organizations(
        self,
        status: Optional[str] = 'active',
        verification_status: Optional[str] = None,
        domain_filter: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List organizations with optional filtering.
        
        Args:
            status: Filter by status ('active', 'suspended', 'revoked', or 'all')
            verification_status: Filter by verification status
            domain_filter: Filter by domain (partial match)
            limit: Maximum results to return
            offset: Offset for pagination
            
        Returns:
            Dict with organizations list and count
        """
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Build query dynamically
            where_clauses = []
            params = []
            
            if status and status != 'all':
                where_clauses.append("status = %s")
                params.append(status)
            
            if verification_status and verification_status != 'all':
                where_clauses.append("verification_status = %s")
                params.append(verification_status)
            
            if domain_filter:
                where_clauses.append("domain ILIKE %s")
                params.append(f"%{domain_filter}%")
            
            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            
            # Get total count
            count_query = f"SELECT COUNT(*) FROM organizations {where_sql}"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()['count']
            
            # Get organizations
            query = f"""
                SELECT org_id, name, domain, display_name, description,
                       master_public_key_hash, revocation_public_key_hash,
                       key_type, status, verification_status,
                       registered_at, metadata
                FROM organizations
                {where_sql}
                ORDER BY registered_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(query, params + [limit, offset])
            
            organizations = []
            for row in cursor.fetchall():
                org = dict(row)
                org['org_id'] = str(org['org_id'])
                if org.get('registered_at'):
                    org['registered_at'] = org['registered_at'].isoformat()
                if org.get('metadata'):
                    if isinstance(org['metadata'], str):
                        org['metadata'] = json.loads(org['metadata'])
                else:
                    org['metadata'] = {}
                organizations.append(org)
            
            return {
                "organizations": organizations,
                "count": len(organizations),
                "total": total_count,
                "limit": limit,
                "offset": offset
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def revoke_organization(
        self,
        org_id: str,
        reason: str,
        revocation_signature: Optional[str] = None,
        revoked_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Revoke an organization (soft delete).
        
        In Phase 1, cryptographic proof of revocation key ownership is optional.
        Future phases will require valid signature from revocation keypair.
        
        Args:
            org_id: Organization ID to revoke
            reason: Reason for revocation
            revocation_signature: Optional signature proving revocation key ownership
            revoked_by: Optional org_id of the entity performing revocation
            
        Returns:
            Dict with revocation details
            
        Raises:
            OrganizationNotFoundError: If organization not found
            OrganizationRevokedError: If already revoked
        """
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Check current status
            cursor.execute("""
                SELECT status, revocation_public_key
                FROM organizations
                WHERE org_id = %s
            """, (org_id,))
            
            row = cursor.fetchone()
            if not row:
                raise OrganizationNotFoundError(f"Organization with ID '{org_id}' not found")
            
            if row['status'] == 'revoked':
                raise OrganizationRevokedError(f"Organization '{org_id}' is already revoked")
            
            # TODO: In Phase 2+, verify revocation_signature against revocation_public_key
            # For Phase 1, we accept the revocation without cryptographic proof
            
            # Perform revocation
            cursor.execute("""
                UPDATE organizations
                SET status = 'revoked',
                    revoked_at = NOW(),
                    revocation_reason = %s,
                    updated_at = NOW()
            """ + (", revoked_by = %s" if revoked_by else "") + """
                WHERE org_id = %s
                RETURNING org_id, name, domain, revoked_at
            """, (reason, revoked_by, org_id) if revoked_by else (reason, org_id))
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "org_id": str(result['org_id']),
                "name": result['name'],
                "domain": result['domain'],
                "status": "revoked",
                "revoked_at": result['revoked_at'].isoformat(),
                "reason": reason,
                "message": "Organization revoked successfully. All credentials issued by this organization should be considered invalid."
            }
            
        except (OrganizationNotFoundError, OrganizationRevokedError):
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
    
    def suspend_organization(self, org_id: str, reason: str) -> Dict[str, Any]:
        """
        Suspend an organization (temporary deactivation).
        
        Unlike revocation, suspension can be reversed.
        
        Args:
            org_id: Organization ID to suspend
            reason: Reason for suspension
            
        Returns:
            Dict with suspension details
        """
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                UPDATE organizations
                SET status = 'suspended',
                    updated_at = NOW()
                WHERE org_id = %s AND status != 'revoked'
                RETURNING org_id, name, domain, status, updated_at
            """, (org_id,))
            
            result = cursor.fetchone()
            if not result:
                raise OrganizationNotFoundError(f"Organization with ID '{org_id}' not found or already revoked")
            
            conn.commit()
            
            return {
                "org_id": str(result['org_id']),
                "name": result['name'],
                "domain": result['domain'],
                "status": result['status'],
                "reason": reason,
                "suspended_at": result['updated_at'].isoformat(),
                "message": "Organization suspended. Credentials are temporarily invalid but can be reactivated."
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def reactivate_organization(self, org_id: str) -> Dict[str, Any]:
        """
        Reactivate a suspended organization.
        
        Note: Cannot reactivate a revoked organization.
        
        Args:
            org_id: Organization ID to reactivate
            
        Returns:
            Dict with reactivation details
        """
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                UPDATE organizations
                SET status = 'active',
                    updated_at = NOW()
                WHERE org_id = %s AND status = 'suspended'
                RETURNING org_id, name, domain, status, updated_at
            """, (org_id,))
            
            result = cursor.fetchone()
            if not result:
                # Check if org exists but is revoked
                cursor.execute("SELECT status FROM organizations WHERE org_id = %s", (org_id,))
                row = cursor.fetchone()
                if row:
                    raise OrganizationRevokedError(f"Cannot reactivate revoked organization '{org_id}'")
                else:
                    raise OrganizationNotFoundError(f"Organization with ID '{org_id}' not found or not suspended")
            
            conn.commit()
            
            return {
                "org_id": str(result['org_id']),
                "name": result['name'],
                "domain": result['domain'],
                "status": result['status'],
                "reactivated_at": result['updated_at'].isoformat(),
                "message": "Organization reactivated. Credentials are now valid again."
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def is_organization_active(self, org_id: str) -> bool:
        """
        Check if an organization is active.
        
        Args:
            org_id: Organization ID
            
        Returns:
            True if organization exists and is active
        """
        try:
            org = self.get_organization(org_id)
            return org.get('status') == 'active'
        except OrganizationNotFoundError:
            return False
    
    def verify_key_ownership(
        self,
        org_id: str,
        message: str,
        signature: str,
        key_type: str = 'master'  # 'master' or 'revocation'
    ) -> bool:
        """
        Verify that a signature was created with the organization's key.
        
        This is a placeholder for Phase 2+ when we implement full
        cryptographic verification of organization signatures.
        
        Args:
            org_id: Organization ID
            message: The message that was signed
            signature: The signature to verify
            key_type: Which key to verify against ('master' or 'revocation')
            
        Returns:
            True if signature is valid
        """
        # TODO: Implement full cryptographic verification in Phase 2+
        # For Phase 1, this is a stub that always returns True
        # Future implementation will:
        # 1. Get the organization's public key
        # 2. Use appropriate verification (secp256k1 or ed25519)
        # 3. Return True only if signature is cryptographically valid
        return True


# Convenience functions for direct use
def register_organization(
    name: str,
    domain: str,
    master_public_key: str,
    revocation_public_key: str,
    key_type: str,
    **kwargs
) -> Dict[str, Any]:
    """Convenience function to register an organization."""
    registry = OrganizationRegistry()
    return registry.register_organization(
        name=name,
        domain=domain,
        master_public_key=master_public_key,
        revocation_public_key=revocation_public_key,
        key_type=key_type,
        **kwargs
    )


def get_organization(org_id: str, include_public_keys: bool = False) -> Dict[str, Any]:
    """Convenience function to get an organization."""
    registry = OrganizationRegistry()
    return registry.get_organization(org_id, include_public_keys)


def revoke_organization(org_id: str, reason: str, **kwargs) -> Dict[str, Any]:
    """Convenience function to revoke an organization."""
    registry = OrganizationRegistry()
    return registry.revoke_organization(org_id, reason, **kwargs)


if __name__ == "__main__":
    # Test functions
    registry = OrganizationRegistry()
    
    # List organizations
    orgs = registry.list_organizations()
    print(f"Registered organizations: {orgs['total']}")
    for org in orgs['organizations'][:5]:
        print(f"  - {org['name']} ({org['domain']}) - {org['status']}")
