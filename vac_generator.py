import uuid
#!/usr/bin/env python3
"""
VAC (Verified Agent Credential) Generator
Observer Protocol VAC Specification v0.3

Generates cryptographically signed VAC credentials with core fields and extensions.
"""

import json
import hashlib
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
import psycopg2
import psycopg2.extras

# Import crypto verification functions
import sys
import os
# Use environment variable for workspace path, with sensible default
OP_WORKSPACE_PATH = os.environ.get('OP_WORKSPACE_PATH', os.path.expanduser('~/.openclaw/workspace/observer-protocol'))
sys.path.insert(0, OP_WORKSPACE_PATH)
from crypto_verification import (
    detect_key_type,
    cache_public_key
)

DB_URL = "postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db"
VAC_VERSION = "1.0.0"
VAC_MAX_AGE_DAYS = 7
VAC_REFRESH_HOURS = 24


@dataclass
class VACCore:
    """Core VAC fields - OP-verified cryptographic facts."""
    agent_id: str
    total_transactions: int
    total_volume_sats: int
    unique_counterparties: int
    rails_used: List[str]
    first_transaction_at: Optional[str] = None
    last_transaction_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        result = {
            "agent_id": self.agent_id,
            "total_transactions": self.total_transactions,
            "total_volume_sats": self.total_volume_sats,
            "unique_counterparty_count": self.unique_counterparties,
            "rails_used": self.rails_used,
        }
        if self.first_transaction_at:
            result["first_transaction_at"] = self.first_transaction_at
        if self.last_transaction_at:
            result["last_transaction_at"] = self.last_transaction_at
        return result


@dataclass
class PartnerAttestation:
    """Partner attestation claim."""
    partner_id: str
    partner_name: str
    partner_type: str
    claims: Dict[str, Any]
    issued_at: str
    expires_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        result = {
            "partner_id": self.partner_id,
            "partner_name": self.partner_name,
            "partner_type": self.partner_type,
            "claims": self.claims,
            "issued_at": self.issued_at,
        }
        if self.expires_at:
            result["expires_at"] = self.expires_at
        return result


@dataclass
class CounterpartyMetadata:
    """Counterparty metadata hash entry."""
    counterparty_id: str
    metadata_hash: str
    merkle_root: Optional[str] = None
    ipfs_cid: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        result = {
            "counterparty_id": self.counterparty_id,
            "metadata_hash": self.metadata_hash,
        }
        if self.merkle_root:
            result["merkle_root"] = self.merkle_root
        if self.ipfs_cid:
            result["ipfs_cid"] = self.ipfs_cid
        return result


@dataclass
class VACExtensions:
    """VAC Extensions - partner attestations and counterparty metadata."""
    partner_attestations: List[PartnerAttestation] = field(default_factory=list)
    counterparty_metadata: List[CounterpartyMetadata] = field(default_factory=list)
    merkle_root: Optional[str] = None
    
    def to_dict(self) -> Optional[Dict[str, Any]]:
        """Convert to dictionary, returning None if empty."""
        result = {}
        
        if self.partner_attestations:
            result["partner_attestations"] = [a.to_dict() for a in self.partner_attestations]
        
        if self.counterparty_metadata:
            result["counterparty_metadata"] = [m.to_dict() for m in self.counterparty_metadata]
        
        if self.merkle_root:
            result["merkle_root"] = self.merkle_root
        
        return result if result else None


@dataclass
class VACCredential:
    """Complete VAC credential document."""
    version: str
    issued_at: str
    expires_at: str
    credential_id: str
    core: VACCore
    extensions: Optional[VACExtensions] = None
    signature: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to canonical dictionary format (sorted keys)."""
        result = {
            "version": self.version,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "credential_id": self.credential_id,
            "core": self.core.to_dict(),
        }
        
        if self.extensions:
            ext_dict = self.extensions.to_dict()
            if ext_dict:
                result["extensions"] = ext_dict
        
        if self.signature:
            result["signature"] = self.signature
        
        return result
    
    def canonical_json(self) -> str:
        """Generate canonical JSON for signing (sorted keys, no whitespace)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'))
    
    def compute_hash(self) -> str:
        """Compute SHA256 hash of canonical JSON."""
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


class VACGenerator:
    """Generates VAC credentials for agents."""
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
        self._op_signing_key = None  # Loaded from environment or secure storage
    
    def _get_db_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.db_url)
    
    def _load_op_signing_key(self) -> str:
        """Load OP signing key from secure storage."""
        # In production, load from environment variable or HSM
        import os
        key = os.environ.get('OP_SIGNING_KEY')
        if not key:
            raise ValueError("OP_SIGNING_KEY environment variable not set")
        return key

    def _load_op_public_key(self) -> str:
        """Load OP public key from environment.

        Bug #3 Fix: Use public key for verification, not private key.
        Set OP_PUBLIC_KEY in environment (derive from OP_SIGNING_KEY once).
        """
        import os
        public_key = os.environ.get('OP_PUBLIC_KEY')
        if not public_key:
            raise ValueError("OP_PUBLIC_KEY environment variable not set. "
                           "Derive the public key from OP_SIGNING_KEY and set OP_PUBLIC_KEY.")
        return public_key
    
    def _sign_vac(self, vac: VACCredential) -> str:
        """
        Sign VAC payload with OP's signing key.
        
        Returns hex-encoded signature.
        """
        # Get canonical JSON for signing
        canonical = vac.canonical_json()
        message_bytes = canonical.encode()
        
        # Load signing key
        signing_key_hex = self._load_op_signing_key()
        
        # Determine key type and sign accordingly
        key_type = detect_key_type(signing_key_hex)
        
        if key_type == 'ed25519':
            return self._sign_ed25519(message_bytes, signing_key_hex)
        elif key_type == 'secp256k1':
            return self._sign_secp256k1(message_bytes, signing_key_hex)
        else:
            raise ValueError(f"Unsupported key type: {key_type}")
    
    def _sign_ed25519(self, message: bytes, private_key_hex: str) -> str:
        """Sign message with Ed25519."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        
        private_key_bytes = bytes.fromhex(private_key_hex)
        private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        signature = private_key.sign(message)
        return signature.hex()
    
    def _sign_secp256k1(self, message: bytes, private_key_hex: str) -> str:
        """Sign message with SECP256k1."""
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        
        private_key_bytes = bytes.fromhex(private_key_hex)
        private_key = ec.derive_private_key(
            int.from_bytes(private_key_bytes, 'big'),
            ec.SECP256K1()
        )
        signature = private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        return signature.hex()
    
    def _aggregate_core_fields(self, agent_id: str) -> VACCore:
        """Aggregate core VAC fields from transaction database."""
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Get transaction aggregates
            # Fix #12: Use bucket midpoints when actual amount is not available
            # Bucket midpoints: micro=500, small=5500, medium=55000, large=500000
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_transactions,
                    COALESCE(SUM(
                        CASE 
                            WHEN metadata->>'amount_sats' IS NOT NULL 
                            THEN (metadata->>'amount_sats')::bigint 
                            WHEN amount_bucket = 'micro' THEN 500
                            WHEN amount_bucket = 'small' THEN 5500
                            WHEN amount_bucket = 'medium' THEN 55000
                            WHEN amount_bucket = 'large' THEN 500000
                            ELSE 0 
                        END
                    ), 0) as total_volume_sats,
                    COUNT(DISTINCT counterparty_id) as unique_counterparties
                FROM verified_events
                WHERE agent_id = %s AND verified = TRUE
            """, (agent_id,))
            
            agg = cursor.fetchone()
            
            # Get unique rails used
            cursor.execute("""
                SELECT DISTINCT protocol
                FROM verified_events
                WHERE agent_id = %s AND verified = TRUE
            """, (agent_id,))
            
            rails = [row['protocol'] for row in cursor.fetchall()]
            
            # Get first and last transaction timestamps
            cursor.execute("""
                SELECT 
                    MIN(created_at) as first_transaction,
                    MAX(created_at) as last_transaction
                FROM verified_events
                WHERE agent_id = %s AND verified = TRUE
            """, (agent_id,))
            
            timestamps = cursor.fetchone()
            
            return VACCore(
                agent_id=agent_id,
                total_transactions=agg['total_transactions'] or 0,
                total_volume_sats=agg['total_volume_sats'] or 0,
                unique_counterparties=agg['unique_counterparties'] or 0,
                rails_used=rails,
                first_transaction_at=timestamps['first_transaction'].isoformat() if timestamps['first_transaction'] else None,
                last_transaction_at=timestamps['last_transaction'].isoformat() if timestamps['last_transaction'] else None
            )
            
        finally:
            cursor.close()
            conn.close()
    
    def _load_partner_attestations(self, agent_id: str, credential_id: Optional[str] = None) -> List[PartnerAttestation]:
        """Load partner attestations for agent."""
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT 
                    pa.attestation_id,
                    pa.claims,
                    pa.issued_at,
                    pa.expires_at,
                    pr.partner_id,
                    pr.partner_name,
                    pr.partner_type
                FROM partner_attestations pa
                JOIN partner_registry pr ON pr.partner_id = pa.partner_id
                JOIN vac_credentials vc ON vc.credential_id = pa.credential_id
                WHERE vc.agent_id = %s 
                  AND vc.is_revoked = FALSE
                  AND (pa.expires_at IS NULL OR pa.expires_at > NOW())
                ORDER BY pa.issued_at DESC
            """, (agent_id,))
            
            attestations = []
            for row in cursor.fetchall():
                attestations.append(PartnerAttestation(
                    partner_id=str(row['partner_id']),
                    partner_name=row['partner_name'],
                    partner_type=row['partner_type'],
                    claims=row['claims'],
                    issued_at=row['issued_at'].isoformat(),
                    expires_at=row['expires_at'].isoformat() if row['expires_at'] else None
                ))
            
            return attestations
            
        finally:
            cursor.close()
            conn.close()
    
    def _load_counterparty_metadata(self, credential_id: str) -> Tuple[List[CounterpartyMetadata], Optional[str]]:
        """Load counterparty metadata hashes for credential."""
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT 
                    counterparty_id,
                    metadata_hash,
                    merkle_root,
                    ipfs_cid
                FROM counterparty_metadata
                WHERE credential_id = %s
                ORDER BY counterparty_id
            """, (credential_id,))
            
            metadata = []
            merkle_root = None
            
            for row in cursor.fetchall():
                metadata.append(CounterpartyMetadata(
                    counterparty_id=row['counterparty_id'],
                    metadata_hash=row['metadata_hash'],
                    merkle_root=row['merkle_root'],
                    ipfs_cid=row['ipfs_cid']
                ))
                if row['merkle_root'] and not merkle_root:
                    merkle_root = row['merkle_root']
            
            return metadata, merkle_root
            
        finally:
            cursor.close()
            conn.close()
    
    def generate_vac(self, agent_id: str, include_extensions: bool = True) -> VACCredential:
        """
        Generate a new VAC credential for an agent.
        
        Args:
            agent_id: The agent's unique identifier
            include_extensions: Whether to include partner attestations and counterparty metadata
            
        Returns:
            VACCredential: The generated and signed VAC credential
        """
        # Generate credential ID
        credential_id = str(uuid.uuid4())
        
        # Calculate timestamps
        issued_at = datetime.now(ZoneInfo("UTC"))
        expires_at = issued_at + timedelta(days=VAC_MAX_AGE_DAYS)
        
        # Aggregate core fields
        core = self._aggregate_core_fields(agent_id)
        
        # Initialize extensions
        extensions = None
        if include_extensions:
            # Load partner attestations
            attestations = self._load_partner_attestations(agent_id)
            
            # Create extensions object
            extensions = VACExtensions(
                partner_attestations=attestations,
                counterparty_metadata=[],  # Will be populated after credential is stored
                merkle_root=None
            )
        
        # Create VAC credential
        vac = VACCredential(
            version=VAC_VERSION,
            issued_at=issued_at.isoformat(),
            expires_at=expires_at.isoformat(),
            credential_id=credential_id,
            core=core,
            extensions=extensions
        )
        
        # Sign the VAC
        signature = self._sign_vac(vac)
        vac.signature = signature
        
        # Store in database
        self._store_vac(vac, agent_id)
        
        return vac
    
    def _store_vac(self, vac: VACCredential, agent_id: str):
        """Store VAC credential in database."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Insert credential
            cursor.execute("""
                INSERT INTO vac_credentials (
                    credential_id, agent_id, vac_version,
                    total_transactions, total_volume_sats, unique_counterparties,
                    rails_used, first_transaction_at, last_transaction_at,
                    issued_at, expires_at, op_signature, vac_payload_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                vac.credential_id,
                agent_id,
                vac.version,
                vac.core.total_transactions,
                vac.core.total_volume_sats,
                vac.core.unique_counterparties,
                vac.core.rails_used,
                vac.core.first_transaction_at,
                vac.core.last_transaction_at,
                vac.issued_at,
                vac.expires_at,
                vac.signature,
                vac.compute_hash()
            ))
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
    
    def get_vac(self, agent_id: str) -> Optional[VACCredential]:
        """
        Retrieve the active VAC credential for an agent.
        
        Args:
            agent_id: The agent's unique identifier
            
        Returns:
            VACCredential if found and valid, None otherwise
        """
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT *
                FROM vac_credentials
                WHERE agent_id = %s 
                  AND is_revoked = FALSE 
                  AND expires_at > NOW()
                ORDER BY issued_at DESC
                LIMIT 1
            """, (agent_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # Load extensions
            extensions = None
            attestations = self._load_partner_attestations(agent_id, row['credential_id'])
            metadata, merkle_root = self._load_counterparty_metadata(row['credential_id'])
            
            if attestations or metadata:
                extensions = VACExtensions(
                    partner_attestations=attestations,
                    counterparty_metadata=metadata,
                    merkle_root=merkle_root
                )
            
            # Reconstruct VAC
            vac = VACCredential(
                version=row['vac_version'],
                issued_at=row['issued_at'].isoformat(),
                expires_at=row['expires_at'].isoformat(),
                credential_id=row['credential_id'],
                core=VACCore(
                    agent_id=row['agent_id'],
                    total_transactions=row['total_transactions'],
                    total_volume_sats=row['total_volume_sats'],
                    unique_counterparties=row['unique_counterparties'],
                    rails_used=row['rails_used'] or [],
                    first_transaction_at=row['first_transaction_at'].isoformat() if row['first_transaction_at'] else None,
                    last_transaction_at=row['last_transaction_at'].isoformat() if row['last_transaction_at'] else None
                ),
                extensions=extensions,
                signature=row['op_signature']
            )
            
            return vac
            
        finally:
            cursor.close()
            conn.close()
    
    def verify_vac(self, vac: VACCredential) -> bool:
        """
        Verify a VAC credential's signature.
        
        Bug #3 Fix: Use public key for verification, not private key.
        
        Args:
            vac: The VAC credential to verify
            
        Returns:
            True if signature is valid, False otherwise
        """
        from crypto_verification import verify_signature
        
        # Get the signature
        signature = vac.signature
        if not signature:
            return False
        
        # Remove signature for verification
        vac_copy = VACCredential(
            version=vac.version,
            issued_at=vac.issued_at,
            expires_at=vac.expires_at,
            credential_id=vac.credential_id,
            core=vac.core,
            extensions=vac.extensions,
            signature=None
        )
        
        # Bug #3 Fix: Use public key for verification
        op_public_key = self._load_op_public_key()
        
        # Verify
        message = vac_copy.canonical_json().encode()
        return verify_signature(message, signature, op_public_key)
    
    def revoke_vac(self, credential_id: str, reason: str, revoked_by: Optional[str] = None):
        """
        Revoke a VAC credential.
        
        Args:
            credential_id: The credential to revoke
            reason: Reason for revocation
            revoked_by: Partner ID of the entity revoking (if not OP)
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Mark credential as revoked
            cursor.execute("""
                UPDATE vac_credentials
                SET is_revoked = TRUE, revoked_at = NOW(), revocation_reason = %s
                WHERE credential_id = %s
                RETURNING agent_id
            """, (reason, credential_id))
            
            result = cursor.fetchone()
            if not result:
                raise ValueError(f"Credential {credential_id} not found")
            
            agent_id = result[0]
            
            # Add to revocation registry
            cursor.execute("""
                INSERT INTO vac_revocation_registry (credential_id, agent_id, revoked_by, reason)
                VALUES (%s, %s, %s, %s)
            """, (credential_id, agent_id, revoked_by, reason))
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()


# Background refresh function
def refresh_all_vacs():
    """Refresh all VACs older than 24 hours."""
    generator = VACGenerator()
    
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    
    try:
        # Find agents needing refresh
        cursor.execute("""
            SELECT DISTINCT agent_id
            FROM observer_agents
            WHERE agent_id NOT IN (
                SELECT agent_id
                FROM vac_credentials
                WHERE is_revoked = FALSE
                  AND issued_at > NOW() - INTERVAL '24 hours'
            )
            AND verified = TRUE
        """)
        
        agents = cursor.fetchall()
        
        refreshed = 0
        for (agent_id,) in agents:
            try:
                generator.generate_vac(agent_id)
                refreshed += 1
            except Exception as e:
                print(f"Failed to refresh VAC for {agent_id}: {e}")
        
        print(f"Refreshed {refreshed} VACs")
        return refreshed
        
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    # Test the generator
    generator = VACGenerator()
    
    # Generate a test VAC (requires existing agent)
    # vac = generator.generate_vac("test_agent_id")
    # print(json.dumps(vac.to_dict(), indent=2))
    
    # Run background refresh
    refresh_all_vacs()
