#!/usr/bin/env python3
"""
Partner Registry Module
Observer Protocol VAC Specification v0.3

Manages partner registration, verification, and attestation issuance.

Partner Types and Trust Levels:
===============================

Partner types define the role and trust level of entities that can issue
attestations attached to VAC (Verified Agent Credential) credentials.

1. CORPO (Legal Entity Partner)
   -----------------------------
   Role: Legal entity verification and compliance attestation
   
   Corpo partners verify that an AI agent is operating under a legal entity
   wrapper (e.g., corporation, LLC, DAO with legal personality). They attest
   to the legal_entity_id associated with an agent.
   
   Trust Level: HIGH - Requires KYB (Know Your Business) verification
   Typical Users: Law firms, compliance services, legal entity registrars
   
   Attestation Claims:
   - legal_entity_id: Unique identifier for the legal entity
   - jurisdiction: Legal jurisdiction (e.g., "US-DE", "CH", "KY")
   - compliance_status: Current compliance state (e.g., "good_standing")
   - entity_type: Type of legal entity (e.g., "C-Corp", "LLC", "DAO")

2. VERIFIER (Identity/Credential Verifier)
   ----------------------------------------
   Role: Identity verification and credential validation
   
   Verifier partners attest to the identity verification level of an agent
   or validate specific credentials held by the agent. They may perform
   KYC (Know Your Customer) checks or verify professional certifications.
   
   Trust Level: MEDIUM-HIGH - Depends on verification methodology
   Typical Users: Identity providers, KYC services, credential issuers
   
   Attestation Claims:
   - verification_level: Level of identity verification performed
   - verification_method: Method used (e.g., "document", "biometric")
   - credentials: List of verified credentials held by agent
   - expiry: When the verification expires

3. COUNTERPARTY (Service Counterparty)
   ------------------------------------
   Role: Service relationship and transaction counterparty attestation
   
   Counterparty partners are entities that have engaged in economic
   transactions with an agent. They can attest to the nature of their
   relationship and the services provided. These attestations help
   establish an agent's transaction history and reputation.
   
   Trust Level: MEDIUM - Based on transaction history and reputation
   Typical Users: Service providers, marketplaces, other AI agents
   
   Attestation Claims:
   - service_type: Type of service provided/received
   - relationship_start: When the relationship began
   - transaction_volume: Aggregate transaction volume
   - rating: Reputation score or rating
   
   Note: Counterparty metadata is stored as hashes anchored to VAC
   credentials for privacy. Actual metadata may be stored off-chain.

4. INFRASTRUCTURE (Infrastructure Provider)
   -----------------------------------------
   Role: Infrastructure and hosting verification
   
   Infrastructure partners attest to the technical infrastructure
   supporting an agent's operation. This includes hosting providers,
   compute providers, and security services.
   
   Trust Level: MEDIUM - Technical verification of infrastructure
   Typical Users: Cloud providers, hosting services, security auditors
   
   Attestation Claims:
   - hosting_provider: Name of infrastructure provider
   - region: Geographic region of operation
   - security_certifications: Security standards met (e.g., "SOC2", "ISO27001")
   - uptime_sla: Service level agreement for availability

Trust Level Summary:
-------------------
- Corpo: HIGH (legal entity verification)
- Verifier: MEDIUM-HIGH (identity/credential verification)
- Counterparty: MEDIUM (service relationship attestation)
- Infrastructure: MEDIUM (technical infrastructure verification)

All partner attestations are cryptographically signed and attached to
VAC credentials as extensions per VAC v0.3 specification.
"""

import json
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import psycopg2
import psycopg2.extras
import sys
import os
# Use environment variable for workspace path, with sensible default
OP_WORKSPACE_PATH = os.environ.get('OP_WORKSPACE_PATH', os.path.expanduser('~/.openclaw/workspace/observer-protocol'))
sys.path.insert(0, OP_WORKSPACE_PATH)
from crypto_verification import (
    verify_signature,
    detect_key_type,
    cache_public_key
)

DB_URL = "postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db"


class PartnerRegistry:
    """Manages partner registration and attestations."""
    
    def __init__(self, db_url: str = DB_URL):
        self.db_url = db_url
    
    def _get_db_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.db_url)
    
    def register_partner(
        self,
        partner_name: str,
        partner_type: str,
        public_key: str,
        webhook_url: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Register a new partner in the registry.
        
        Args:
            partner_name: Unique name for the partner
            partner_type: One of 'corpo', 'verifier', 'counterparty', 'infrastructure'
            public_key: Partner's public key for attestation signing
            webhook_url: Optional webhook URL for revocation events
            metadata: Optional metadata dictionary
            
        Returns:
            Dict with partner_id and registration details
        """
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                INSERT INTO partner_registry (
                    partner_name, partner_type, public_key, webhook_url, metadata
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING partner_id, partner_name, partner_type, registered_at
            """, (partner_name, partner_type, public_key, webhook_url, json.dumps(metadata or {})))
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "partner_id": str(result['partner_id']),
                "partner_name": result['partner_name'],
                "partner_type": result['partner_type'],
                "registered_at": result['registered_at'].isoformat(),
                "status": "registered"
            }
            
        except psycopg2.IntegrityError as e:
            conn.rollback()
            raise ValueError(f"Partner with name '{partner_name}' already exists")
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
    
    def get_partner(self, partner_id: str) -> Optional[Dict[str, Any]]:
        """Get partner details by ID."""
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT partner_id, partner_name, partner_type, public_key,
                       webhook_url, is_active, registered_at, last_verified_at, metadata
                FROM partner_registry
                WHERE partner_id = %s
            """, (partner_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                "partner_id": str(row['partner_id']),
                "partner_name": row['partner_name'],
                "partner_type": row['partner_type'],
                "public_key": row['public_key'],
                "webhook_url": row['webhook_url'],
                "is_active": row['is_active'],
                "registered_at": row['registered_at'].isoformat(),
                "last_verified_at": row['last_verified_at'].isoformat() if row['last_verified_at'] else None,
                "metadata": row['metadata']
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def list_partners(
        self,
        partner_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """List partners with optional filtering."""
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            query = """
                SELECT partner_id, partner_name, partner_type, public_key,
                       is_active, registered_at
                FROM partner_registry
                WHERE 1=1
            """
            params = []
            
            if partner_type:
                query += " AND partner_type = %s"
                params.append(partner_type)
            
            if is_active is not None:
                query += " AND is_active = %s"
                params.append(is_active)
            
            query += " ORDER BY registered_at DESC"
            
            cursor.execute(query, params)
            
            return [{
                "partner_id": str(row['partner_id']),
                "partner_name": row['partner_name'],
                "partner_type": row['partner_type'],
                "public_key": row['public_key'],
                "is_active": row['is_active'],
                "registered_at": row['registered_at'].isoformat()
            } for row in cursor.fetchall()]
            
        finally:
            cursor.close()
            conn.close()
    
    def verify_partner_key(self, partner_id: str) -> bool:
        """
        Verify a partner's public key is valid.
        
        This performs basic validation on the key format.
        """
        partner = self.get_partner(partner_id)
        if not partner:
            return False
        
        public_key = partner['public_key']
        key_type = detect_key_type(public_key)
        
        if key_type == 'unknown':
            return False
        
        # Update last_verified_at
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE partner_registry
                SET last_verified_at = NOW()
                WHERE partner_id = %s
            """, (partner_id,))
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        
        return True
    
    def issue_attestation(
        self,
        partner_id: str,
        agent_id: str,
        claims: Dict[str, Any],
        credential_id: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        attestation_signature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Issue a partner attestation for an agent.
        
        Args:
            partner_id: ID of the issuing partner
            agent_id: ID of the agent being attested
            claims: JSON object containing attested claims
            credential_id: Optional specific VAC credential to attach to
            expires_in_days: Optional expiration time for attestation
            attestation_signature: Partner's signature of the attestation
            
        Returns:
            Dict with attestation details
        """
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Verify partner exists and is active
            cursor.execute("""
                SELECT partner_id, public_key, is_active
                FROM partner_registry
                WHERE partner_id = %s
            """, (partner_id,))
            
            partner = cursor.fetchone()
            if not partner:
                raise ValueError(f"Partner {partner_id} not found")
            
            if not partner['is_active']:
                raise ValueError(f"Partner {partner_id} is not active")
            
            # If no credential_id provided, get or create active VAC
            if not credential_id:
                cursor.execute("""
                    SELECT credential_id
                    FROM vac_credentials
                    WHERE agent_id = %s
                      AND is_revoked = FALSE
                      AND expires_at > NOW()
                    ORDER BY issued_at DESC
                    LIMIT 1
                """, (agent_id,))
                
                cred_row = cursor.fetchone()
                if cred_row:
                    credential_id = cred_row['credential_id']
                else:
                    # Generate new VAC (requires vac_generator)
                    from vac_generator import VACGenerator
                    generator = VACGenerator()
                    vac = generator.generate_vac(agent_id, include_extensions=False)
                    credential_id = vac.credential_id
            
            # Calculate expiration
            expires_at = None
            if expires_in_days:
                expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
            
            # Create attestation hash
            attestation_data = {
                "partner_id": partner_id,
                "agent_id": agent_id,
                "claims": claims,
                "issued_at": datetime.utcnow().isoformat()
            }
            attestation_hash = hashlib.sha256(
                json.dumps(attestation_data, sort_keys=True).encode()
            ).hexdigest()
            
            # Bug #2 Fix: Verify attestation signature cryptographically
            if not attestation_signature:
                raise ValueError("Attestation signature required")
            
            # Verify the attestation signature
            attestation_hash_bytes = bytes.fromhex(attestation_hash)
            is_valid = verify_signature(attestation_hash_bytes, attestation_signature, partner['public_key'])
            if not is_valid:
                raise ValueError("Attestation signature verification failed")
            
            # Insert attestation
            cursor.execute("""
                INSERT INTO partner_attestations (
                    credential_id, partner_id, claims,
                    attestation_signature, attestation_hash, expires_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING attestation_id, issued_at
            """, (
                credential_id, partner_id, json.dumps(claims),
                attestation_signature, attestation_hash, expires_at
            ))
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "attestation_id": str(result['attestation_id']),
                "credential_id": credential_id,
                "partner_id": partner_id,
                "agent_id": agent_id,
                "claims": claims,
                "issued_at": result['issued_at'].isoformat(),
                "expires_at": expires_at.isoformat() if expires_at else None,
                "attestation_hash": attestation_hash
            }
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
    
    def get_attestations_for_agent(
        self,
        agent_id: str,
        partner_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all attestations for an agent."""
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            query = """
                SELECT 
                    pa.attestation_id,
                    pa.credential_id,
                    pa.claims,
                    pa.issued_at,
                    pa.expires_at,
                    pa.attestation_hash,
                    pr.partner_id,
                    pr.partner_name,
                    pr.partner_type
                FROM partner_attestations pa
                JOIN vac_credentials vc ON vc.credential_id = pa.credential_id
                JOIN partner_registry pr ON pr.partner_id = pa.partner_id
                WHERE vc.agent_id = %s
                  AND vc.is_revoked = FALSE
            """
            params = [agent_id]
            
            if partner_type:
                query += " AND pr.partner_type = %s"
                params.append(partner_type)
            
            query += " ORDER BY pa.issued_at DESC"
            
            cursor.execute(query, params)
            
            return [{
                "attestation_id": str(row['attestation_id']),
                "credential_id": row['credential_id'],
                "partner_id": str(row['partner_id']),
                "partner_name": row['partner_name'],
                "partner_type": row['partner_type'],
                "claims": row['claims'],
                "issued_at": row['issued_at'].isoformat(),
                "expires_at": row['expires_at'].isoformat() if row['expires_at'] else None,
                "attestation_hash": row['attestation_hash']
            } for row in cursor.fetchall()]
            
        finally:
            cursor.close()
            conn.close()
    
    def validate_quality_claims(self, claims: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate quality claims for counterparty attestations.
        
        Required fields per VAC v0.3.2 spec §8.6:
        - completion_status: enum ["complete", "partial", "failed", "cancelled"]
        - accuracy_rating: integer 1-5
        - dispute_raised: boolean
        - payment_settled: boolean
        - quality_schema_version: string (e.g., "0.3.2")
        
        Conditional field:
        - completion_percentage: integer 0-100 (required when completion_status = "partial")
        
        Optional fields:
        - notes_hash: sha256 hash of freetext notes
        - notes_retrieval_url: URL for retrieving notes via AT ARS endpoint
        
        Args:
            claims: The quality claims to validate
            
        Returns:
            Dict with validation result: {"valid": bool, "errors": list}
        """
        errors = []
        
        # Required fields
        required_fields = [
            "completion_status",
            "accuracy_rating", 
            "dispute_raised",
            "payment_settled",
            "quality_schema_version"
        ]
        
        for field in required_fields:
            if field not in claims:
                errors.append(f"Missing required field: {field}")
        
        # Validate completion_status enum
        valid_completion_statuses = ["complete", "partial", "failed", "cancelled"]
        if "completion_status" in claims:
            if claims["completion_status"] not in valid_completion_statuses:
                errors.append(
                    f"Invalid completion_status: {claims['completion_status']}. "
                    f"Must be one of: {', '.join(valid_completion_statuses)}"
                )
        
        # Validate accuracy_rating (1-5)
        if "accuracy_rating" in claims:
            try:
                rating = int(claims["accuracy_rating"])
                if rating < 1 or rating > 5:
                    errors.append("accuracy_rating must be between 1 and 5")
            except (ValueError, TypeError):
                errors.append("accuracy_rating must be an integer between 1 and 5")
        
        # Validate dispute_raised is boolean
        if "dispute_raised" in claims:
            if not isinstance(claims["dispute_raised"], bool):
                errors.append("dispute_raised must be a boolean")
        
        # Validate payment_settled is boolean
        if "payment_settled" in claims:
            if not isinstance(claims["payment_settled"], bool):
                errors.append("payment_settled must be a boolean")
        
        # Validate completion_percentage when completion_status = "partial"
        if claims.get("completion_status") == "partial":
            if "completion_percentage" not in claims:
                errors.append("completion_percentage is required when completion_status is 'partial'")
            else:
                try:
                    percentage = int(claims["completion_percentage"])
                    if percentage < 0 or percentage > 100:
                        errors.append("completion_percentage must be between 0 and 100")
                except (ValueError, TypeError):
                    errors.append("completion_percentage must be an integer between 0 and 100")
        
        # Validate notes_hash format (if provided, must be valid sha256 hex)
        if "notes_hash" in claims:
            notes_hash = claims["notes_hash"]
            if not isinstance(notes_hash, str):
                errors.append("notes_hash must be a string")
            elif len(notes_hash) != 64:
                errors.append("notes_hash must be a 64-character hex string (sha256)")
            else:
                try:
                    int(notes_hash, 16)  # Validate hex
                except ValueError:
                    errors.append("notes_hash must be a valid hexadecimal string")
        
        # Validate notes_retrieval_url format (if provided)
        if "notes_retrieval_url" in claims:
            url = claims["notes_retrieval_url"]
            if not isinstance(url, str):
                errors.append("notes_retrieval_url must be a string")
            elif not url.startswith(("https://", "http://")):
                errors.append("notes_retrieval_url must be a valid URL")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def submit_quality_claim(
        self,
        partner_id: str,
        agent_id: str,
        transaction_id: str,
        quality_claims: Dict[str, Any],
        credential_id: Optional[str] = None,
        attestation_signature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submit a quality claim attestation from a counterparty.
        
        Per VAC v0.3.2 spec §8.6, quality claims provide attestations about
        transaction quality for AT-ARS reputation scoring.
        
        Args:
            partner_id: ID of the counterparty partner submitting the claim
            agent_id: ID of the agent being rated
            transaction_id: Reference to the specific transaction
            quality_claims: Quality claim fields per §8.6 spec
            credential_id: Optional specific VAC credential to attach to
            attestation_signature: Partner's cryptographic signature
            
        Returns:
            Dict with attestation details including quality_claims validation
        """
        # Validate quality claims structure
        validation = self.validate_quality_claims(quality_claims)
        if not validation["valid"]:
            raise ValueError(f"Invalid quality_claims: {'; '.join(validation['errors'])}")
        
        # Build claims with quality_claims nested
        claims = {
            "transaction_id": transaction_id,
            "quality_claims": quality_claims,
            "attestation_type": "quality_claim"
        }
        
        # Issue attestation via parent method
        return self.issue_attestation(
            partner_id=partner_id,
            agent_id=agent_id,
            claims=claims,
            credential_id=credential_id,
            expires_in_days=None,  # Quality claims don't expire by default
            attestation_signature=attestation_signature
        )
    
    def add_counterparty_metadata(
        self,
        credential_id: str,
        counterparty_id: str,
        metadata: Dict[str, Any],
        ipfs_cid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add counterparty metadata hash to a VAC credential.
        
        Args:
            credential_id: The VAC credential ID
            counterparty_id: Hashed counterparty identifier
            metadata: The metadata (will be hashed, not stored directly)
            ipfs_cid: Optional IPFS CID for off-chain metadata storage
            
        Returns:
            Dict with metadata hash details
        """
        # Hash the metadata
        metadata_hash = hashlib.sha256(
            json.dumps(metadata, sort_keys=True).encode()
        ).hexdigest()
        
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                INSERT INTO counterparty_metadata (
                    credential_id, counterparty_id, metadata_hash, ipfs_cid
                ) VALUES (%s, %s, %s, %s)
                RETURNING metadata_id, created_at
            """, (credential_id, counterparty_id, metadata_hash, ipfs_cid))
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "metadata_id": str(result['metadata_id']),
                "credential_id": credential_id,
                "counterparty_id": counterparty_id,
                "metadata_hash": metadata_hash,
                "ipfs_cid": ipfs_cid,
                "created_at": result['created_at'].isoformat()
            }
            
        except psycopg2.IntegrityError:
            conn.rollback()
            # Update existing
            cursor.execute("""
                UPDATE counterparty_metadata
                SET metadata_hash = %s, ipfs_cid = %s
                WHERE credential_id = %s AND counterparty_id = %s
                RETURNING metadata_id, created_at
            """, (metadata_hash, ipfs_cid, credential_id, counterparty_id))
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "metadata_id": str(result['metadata_id']),
                "credential_id": credential_id,
                "counterparty_id": counterparty_id,
                "metadata_hash": metadata_hash,
                "ipfs_cid": ipfs_cid,
                "created_at": result['created_at'].isoformat(),
                "updated": True
            }
        finally:
            cursor.close()
            conn.close()
    
    def deactivate_partner(self, partner_id: str) -> bool:
        """Deactivate a partner."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE partner_registry
                SET is_active = FALSE
                WHERE partner_id = %s
            """, (partner_id,))
            
            conn.commit()
            return cursor.rowcount > 0
        finally:
            cursor.close()
            conn.close()
    
    def store_notes_hash(
        self,
        transaction_id: str,
        notes_hash: str,
        partner_id: str,
        retrieval_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Store a notes hash for later retrieval via AT ARS endpoint.
        
        Per VAC v0.3.2 spec §8.6, notes hashes are stored with the transaction
        and can be verified when notes are submitted later via POST /ars/notes/{transaction_id}
        
        Args:
            transaction_id: The transaction being attested to
            notes_hash: SHA256 hash of the freetext notes
            partner_id: The partner submitting the notes hash
            retrieval_url: Optional AT ARS URL for notes retrieval
            
        Returns:
            Dict with notes storage details
        """
        # Validate hash format
        if not isinstance(notes_hash, str) or len(notes_hash) != 64:
            raise ValueError("notes_hash must be a 64-character hex string")
        try:
            int(notes_hash, 16)
        except ValueError:
            raise ValueError("notes_hash must be valid hexadecimal")
        
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                INSERT INTO quality_claims_notes (
                    transaction_id,
                    notes_hash,
                    partner_id,
                    retrieval_url,
                    retrieval_status,
                    created_at
                ) VALUES (%s, %s, %s, %s, 'pending', NOW())
                ON CONFLICT (transaction_id, partner_id) 
                DO UPDATE SET
                    notes_hash = EXCLUDED.notes_hash,
                    retrieval_url = EXCLUDED.retrieval_url,
                    updated_at = NOW()
                RETURNING notes_id, created_at, retrieval_status
            """, (transaction_id, notes_hash, partner_id, retrieval_url))
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "notes_id": str(result['notes_id']),
                "transaction_id": transaction_id,
                "notes_hash": notes_hash,
                "partner_id": partner_id,
                "retrieval_url": retrieval_url,
                "retrieval_status": result['retrieval_status'],
                "created_at": result['created_at'].isoformat()
            }
            
        finally:
            cursor.close()
            conn.close()
    
    def verify_and_retrieve_notes(
        self,
        transaction_id: str,
        notes_text: str,
        submitted_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify submitted notes text against stored hash and update retrieval status.
        
        This implements the POST /ars/notes/{transaction_id} endpoint logic.
        The submitted text is hashed and compared to the stored notes_hash.
        
        Args:
            transaction_id: The transaction ID for the notes
            notes_text: The freetext notes being submitted
            submitted_by: Optional identifier of who submitted the notes
            
        Returns:
            Dict with verification result and updated status
        """
        # Compute hash of submitted text
        computed_hash = hashlib.sha256(notes_text.encode('utf-8')).hexdigest()
        
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            # Find the stored notes hash
            cursor.execute("""
                SELECT notes_id, notes_hash, partner_id, retrieval_status
                FROM quality_claims_notes
                WHERE transaction_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (transaction_id,))
            
            stored = cursor.fetchone()
            if not stored:
                raise ValueError(f"No notes hash found for transaction {transaction_id}")
            
            # Verify hash matches
            hash_match = computed_hash == stored['notes_hash']
            
            if hash_match:
                # Update retrieval status to 'retrieved'
                cursor.execute("""
                    UPDATE quality_claims_notes
                    SET retrieval_status = 'retrieved',
                        retrieved_at = NOW(),
                        retrieved_by = %s
                    WHERE notes_id = %s
                """, (submitted_by, stored['notes_id']))
                conn.commit()
                
                return {
                    "verified": True,
                    "transaction_id": transaction_id,
                    "notes_id": str(stored['notes_id']),
                    "hash_match": True,
                    "retrieval_status": "retrieved",
                    "message": "Notes verified and retrieval status updated"
                }
            else:
                return {
                    "verified": False,
                    "transaction_id": transaction_id,
                    "notes_id": str(stored['notes_id']),
                    "hash_match": False,
                    "expected_hash": stored['notes_hash'],
                    "computed_hash": computed_hash,
                    "retrieval_status": stored['retrieval_status'],
                    "message": "Hash mismatch - submitted notes do not match stored hash"
                }
                
        finally:
            cursor.close()
            conn.close()
    
    def get_notes_retrieval_status(
        self,
        transaction_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the retrieval status for notes on a transaction.
        
        Args:
            transaction_id: The transaction ID to check
            
        Returns:
            Dict with retrieval status, or None if no notes exist
        """
        conn = self._get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT 
                    notes_id,
                    transaction_id,
                    notes_hash,
                    partner_id,
                    retrieval_url,
                    retrieval_status,
                    created_at,
                    retrieved_at,
                    retrieved_by
                FROM quality_claims_notes
                WHERE transaction_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (transaction_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                "notes_id": str(row['notes_id']),
                "transaction_id": row['transaction_id'],
                "notes_hash": row['notes_hash'],
                "partner_id": row['partner_id'],
                "retrieval_url": row['retrieval_url'],
                "retrieval_status": row['retrieval_status'],
                "created_at": row['created_at'].isoformat(),
                "retrieved_at": row['retrieved_at'].isoformat() if row['retrieved_at'] else None,
                "retrieved_by": row['retrieved_by']
            }
            
        finally:
            cursor.close()
            conn.close()


# Convenience functions for Corpo integration
def register_corpo_partner(
    legal_entity_name: str,
    public_key: str,
    webhook_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Register a Corpo legal wrapper partner.
    
    This is a convenience function for registering Corpo partners
    which handle legal_entity_id attestations.
    """
    registry = PartnerRegistry()
    return registry.register_partner(
        partner_name=legal_entity_name,
        partner_type='corpo',
        public_key=public_key,
        webhook_url=webhook_url,
        metadata={"service": "legal_entity_verification"}
    )


def issue_corpo_attestation(
    partner_id: str,
    agent_id: str,
    legal_entity_id: str,
    jurisdiction: Optional[str] = None,
    compliance_status: Optional[str] = None,
    **additional_claims
) -> Dict[str, Any]:
    """
    Issue a Corpo legal entity attestation.
    
    This attaches the legal_entity_id to the agent's VAC via partner attestations.
    Per v0.3 spec, legal_entity_id is moved from agent table to extensions.
    """
    registry = PartnerRegistry()
    
    claims = {
        "legal_entity_id": legal_entity_id,
        **additional_claims
    }
    
    if jurisdiction:
        claims["jurisdiction"] = jurisdiction
    if compliance_status:
        claims["compliance_status"] = compliance_status
    
    return registry.issue_attestation(
        partner_id=partner_id,
        agent_id=agent_id,
        claims=claims
    )


if __name__ == "__main__":
    # Test functions
    registry = PartnerRegistry()
    
    # List all partners
    partners = registry.list_partners()
    print(f"Registered partners: {len(partners)}")
    for p in partners:
        print(f"  - {p['partner_name']} ({p['partner_type']})")
