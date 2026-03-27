#!/usr/bin/env python3
"""
Attestation Scoping and Hybrid Trust Model
Observer Protocol - Fix #7

This module implements proper attestation scoping with a hybrid trust model
differentiating between different levels of attestations based on partner type,
verification depth, and cryptographic assurance.

Trust Levels:
===============

1. LEVEL_1 (Self-Attested)
   - Claims made by the agent itself
   - Minimal trust, useful for bootstrapping
   - No external verification

2. LEVEL_2 (Counterparty Attested)
   - Claims attested by transaction counterparties
   - Medium trust based on transaction history
   - Cryptographically signed by counterparty

3. LEVEL_3 (Partner Attested)
   - Claims attested by registered protocol partners
   - Higher trust based on partner reputation
   - Partners have been KYB verified

4. LEVEL_4 (Organization Attested)
   - Claims attested by registered organizations
   - High trust based on organizational verification
   - Organizations have legal entity backing

5. LEVEL_5 (OP Verified)
   - Claims directly verified by Observer Protocol
   - Highest trust level
   - Protocol-level cryptographic verification

Hybrid Model:
=============
The hybrid model combines on-chain and off-chain verification:
- On-chain: Cryptographic signatures, hash commitments
- Off-chain: Partner verification, legal entity checks, reputation scores

Usage:
    from attestation_scoping import (
        AttestationScope,
        HybridAttestation,
        AttestationValidator
    )
    
    # Create a hybrid attestation
    attestation = HybridAttestation(
        agent_id="agent_123",
        trust_level=TrustLevel.LEVEL_3,
        claims={"legal_entity_id": "CORP-456"},
        partner_id="partner_789"
    )
    
    # Validate the attestation
    validator = AttestationValidator()
    result = validator.validate(attestation)
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field


class TrustLevel(Enum):
    """Trust levels for attestations."""
    LEVEL_0 = 0  # No attestation / Revoked
    LEVEL_1 = 1  # Self-attested
    LEVEL_2 = 2  # Counterparty attested
    LEVEL_3 = 3  # Partner attested
    LEVEL_4 = 4  # Organization attested
    LEVEL_5 = 5  # OP verified


class AttestationScope(Enum):
    """Scopes defining what an attestation covers."""
    IDENTITY = "identity"           # Identity verification
    LEGAL_ENTITY = "legal_entity"   # Legal entity wrapper
    COMPLIANCE = "compliance"       # Regulatory compliance
    REPUTATION = "reputation"       # Reputation score
    CAPABILITY = "capability"       # Technical capabilities
    TRANSACTION = "transaction"     # Transaction history
    INFRASTRUCTURE = "infrastructure"  # Infrastructure provider
    CUSTOM = "custom"               # Custom scope


@dataclass
class AttestationProof:
    """Cryptographic proof for an attestation."""
    signature: str
    signer_public_key: str
    timestamp: str
    hash_algorithm: str = "sha256"
    signature_scheme: str = "ecdsa-secp256k1"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature": self.signature,
            "signer_public_key": self.signer_public_key,
            "timestamp": self.timestamp,
            "hash_algorithm": self.hash_algorithm,
            "signature_scheme": self.signature_scheme
        }


@dataclass
class AttestationScopeDetails:
    """Details about the scope of an attestation."""
    scope_type: AttestationScope
    scope_description: str
    valid_from: str
    valid_until: Optional[str] = None
    restrictions: List[str] = field(default_factory=list)
    
    def is_valid(self) -> bool:
        """Check if the attestation is currently valid."""
        now = datetime.utcnow()
        
        valid_from = datetime.fromisoformat(self.valid_from.replace('Z', '+00:00'))
        if valid_from > now:
            return False
        
        if self.valid_until:
            valid_until = datetime.fromisoformat(self.valid_until.replace('Z', '+00:00'))
            if valid_until < now:
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "scope_type": self.scope_type.value,
            "scope_description": self.scope_description,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "restrictions": self.restrictions
        }
        return result


@dataclass
class HybridAttestation:
    """
    Hybrid attestation combining on-chain and off-chain verification.
    
    This is the main data structure for attestation scoping (Fix #7).
    """
    agent_id: str
    trust_level: TrustLevel
    claims: Dict[str, Any]
    scope: AttestationScopeDetails
    proof: Optional[AttestationProof] = None
    
    # Attestor information
    attestor_type: str = ""  # 'self', 'partner', 'organization', 'op'
    attestor_id: Optional[str] = None
    
    # Hybrid model fields
    on_chain_anchor: Optional[str] = None  # Blockchain tx hash or merkle root
    off_chain_evidence: Optional[str] = None  # IPFS hash or URL
    
    # Verification metadata
    verification_depth: int = 0  # How many levels of verification
    reputation_score: Optional[float] = None  # 0.0 - 1.0
    
    def compute_hash(self) -> str:
        """Compute hash of the attestation for signing."""
        data = {
            "agent_id": self.agent_id,
            "trust_level": self.trust_level.value,
            "claims": self.claims,
            "scope": self.scope.to_dict(),
            "attestor_type": self.attestor_type,
            "attestor_id": self.attestor_id
        }
        canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "agent_id": self.agent_id,
            "trust_level": {
                "level": self.trust_level.value,
                "name": self.trust_level.name
            },
            "claims": self.claims,
            "scope": self.scope.to_dict(),
            "attestor": {
                "type": self.attestor_type,
                "id": self.attestor_id
            },
            "hybrid": {
                "on_chain_anchor": self.on_chain_anchor,
                "off_chain_evidence": self.off_chain_evidence
            },
            "verification": {
                "depth": self.verification_depth,
                "reputation_score": self.reputation_score
            }
        }
        
        if self.proof:
            result["proof"] = self.proof.to_dict()
        
        return result
    
    def get_effective_trust_score(self) -> float:
        """
        Calculate effective trust score based on multiple factors.
        
        Returns a score between 0.0 and 1.0 combining:
        - Base trust level (0.5 - 1.0)
        - Verification depth bonus (0.0 - 0.2)
        - Reputation score (if available)
        - Scope validity
        """
        # Base score from trust level (LEVEL_1 = 0.5, LEVEL_5 = 1.0)
        base_score = 0.3 + (self.trust_level.value * 0.14)
        
        # Verification depth bonus
        depth_bonus = min(self.verification_depth * 0.05, 0.2)
        
        # Reputation score (if available)
        reputation = self.reputation_score if self.reputation_score is not None else 0.5
        
        # Scope validity
        scope_valid = 1.0 if self.scope.is_valid() else 0.0
        
        # Combined score
        score = (base_score * 0.4 + depth_bonus + reputation * 0.3 + scope_valid * 0.1)
        
        return min(score, 1.0)


class AttestationValidator:
    """
    Validator for hybrid attestations.
    
    Validates attestations based on:
    - Cryptographic signature verification
    - Trust level requirements
    - Scope validity
    - Attestor reputation
    """
    
    def __init__(self, min_trust_level: TrustLevel = TrustLevel.LEVEL_1):
        self.min_trust_level = min_trust_level
        self._trusted_attestors: set = set()
        self._revoked_attestations: set = set()
    
    def add_trusted_attestor(self, attestor_id: str):
        """Add an attestor to the trusted list."""
        self._trusted_attestors.add(attestor_id)
    
    def revoke_attestation(self, attestation_hash: str):
        """Mark an attestation as revoked."""
        self._revoked_attestations.add(attestation_hash)
    
    def validate(self, attestation: HybridAttestation) -> Dict[str, Any]:
        """
        Validate a hybrid attestation.
        
        Returns validation result with details.
        """
        result = {
            "valid": True,
            "checks": {},
            "errors": []
        }
        
        # Check 1: Trust level meets minimum
        if attestation.trust_level.value < self.min_trust_level.value:
            result["valid"] = False
            result["errors"].append(
                f"Trust level {attestation.trust_level.name} below minimum "
                f"{self.min_trust_level.name}"
            )
        result["checks"]["trust_level"] = attestation.trust_level.value >= self.min_trust_level.value
        
        # Check 2: Scope is valid (not expired)
        scope_valid = attestation.scope.is_valid()
        if not scope_valid:
            result["valid"] = False
            result["errors"].append("Attestation scope has expired or is not yet valid")
        result["checks"]["scope_valid"] = scope_valid
        
        # Check 3: Cryptographic proof (if present)
        if attestation.proof:
            proof_valid = self._verify_proof(attestation)
            if not proof_valid:
                result["valid"] = False
                result["errors"].append("Cryptographic proof verification failed")
            result["checks"]["proof_valid"] = proof_valid
        else:
            result["checks"]["proof_valid"] = None  # No proof to verify
        
        # Check 4: Attestor trust
        attestor_trusted = (
            attestation.attestor_id in self._trusted_attestors
            if attestation.attestor_id
            else attestation.trust_level == TrustLevel.LEVEL_1  # Self-attested
        )
        result["checks"]["attestor_trusted"] = attestor_trusted
        
        # Check 5: Not revoked
        attestation_hash = attestation.compute_hash()
        not_revoked = attestation_hash not in self._revoked_attestations
        if not not_revoked:
            result["valid"] = False
            result["errors"].append("Attestation has been revoked")
        result["checks"]["not_revoked"] = not_revoked
        
        # Calculate effective trust score
        result["trust_score"] = attestation.get_effective_trust_score()
        
        return result
    
    def _verify_proof(self, attestation: HybridAttestation) -> bool:
        """Verify cryptographic proof of attestation."""
        if not attestation.proof:
            return True  # No proof required
        
        try:
            # Import here to avoid circular dependencies
            import sys
            import os
            OP_WORKSPACE_PATH = os.environ.get('OP_WORKSPACE_PATH', 
                os.path.expanduser('~/.openclaw/workspace/observer-protocol'))
            sys.path.insert(0, OP_WORKSPACE_PATH)
            from crypto_verification import verify_signature
            
            # Compute expected hash
            expected_hash = attestation.compute_hash()
            
            # Verify signature
            message = expected_hash.encode()
            signature = attestation.proof.signature
            public_key = attestation.proof.signer_public_key
            
            return verify_signature(message, signature, public_key)
            
        except Exception as e:
            print(f"Proof verification error: {e}")
            return False


class AttestationScopeManager:
    """
    Manager for attestation scoping.
    
    Handles creation, storage, and retrieval of scoped attestations.
    """
    
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url
        self._attestations: Dict[str, HybridAttestation] = {}
    
    def create_self_attestation(
        self,
        agent_id: str,
        claims: Dict[str, Any],
        scope_type: AttestationScope = AttestationScope.IDENTITY
    ) -> HybridAttestation:
        """
        Create a self-attestation (Trust Level 1).
        
        These are claims made by the agent about itself.
        """
        scope = AttestationScopeDetails(
            scope_type=scope_type,
            scope_description=f"Self-attested {scope_type.value}",
            valid_from=datetime.utcnow().isoformat(),
            valid_until=(datetime.utcnow() + timedelta(days=30)).isoformat()
        )
        
        attestation = HybridAttestation(
            agent_id=agent_id,
            trust_level=TrustLevel.LEVEL_1,
            claims=claims,
            scope=scope,
            attestor_type="self",
            attestor_id=agent_id,
            verification_depth=0
        )
        
        return attestation
    
    def create_partner_attestation(
        self,
        agent_id: str,
        partner_id: str,
        claims: Dict[str, Any],
        partner_public_key: str,
        partner_private_key: str,
        scope_type: AttestationScope = AttestationScope.LEGAL_ENTITY
    ) -> HybridAttestation:
        """
        Create a partner attestation (Trust Level 3).
        
        These are claims attested by a registered protocol partner.
        """
        import sys
        import os
        OP_WORKSPACE_PATH = os.environ.get('OP_WORKSPACE_PATH', 
            os.path.expanduser('~/.openclaw/workspace/observer-protocol'))
        sys.path.insert(0, OP_WORKSPACE_PATH)
        from crypto_verification import sign_message_secp256k1
        
        scope = AttestationScopeDetails(
            scope_type=scope_type,
            scope_description=f"Partner-attested {scope_type.value}",
            valid_from=datetime.utcnow().isoformat(),
            valid_until=(datetime.utcnow() + timedelta(days=90)).isoformat()
        )
        
        attestation = HybridAttestation(
            agent_id=agent_id,
            trust_level=TrustLevel.LEVEL_3,
            claims=claims,
            scope=scope,
            attestor_type="partner",
            attestor_id=partner_id,
            verification_depth=1
        )
        
        # Sign the attestation
        hash_to_sign = attestation.compute_hash()
        signature = sign_message_secp256k1(
            hash_to_sign.encode(),
            partner_private_key
        )
        
        attestation.proof = AttestationProof(
            signature=signature,
            signer_public_key=partner_public_key,
            timestamp=datetime.utcnow().isoformat()
        )
        
        return attestation
    
    def create_op_attestation(
        self,
        agent_id: str,
        claims: Dict[str, Any],
        op_signing_key: str,
        op_public_key: str,
        scope_type: AttestationScope = AttestationScope.IDENTITY
    ) -> HybridAttestation:
        """
        Create an OP-verified attestation (Trust Level 5).
        
        These are claims directly verified by the Observer Protocol.
        """
        import sys
        import os
        OP_WORKSPACE_PATH = os.environ.get('OP_WORKSPACE_PATH', 
            os.path.expanduser('~/.openclaw/workspace/observer-protocol'))
        sys.path.insert(0, OP_WORKSPACE_PATH)
        from crypto_verification import sign_message_secp256k1
        
        scope = AttestationScopeDetails(
            scope_type=scope_type,
            scope_description=f"OP-verified {scope_type.value}",
            valid_from=datetime.utcnow().isoformat(),
            valid_until=(datetime.utcnow() + timedelta(days=365)).isoformat()
        )
        
        attestation = HybridAttestation(
            agent_id=agent_id,
            trust_level=TrustLevel.LEVEL_5,
            claims=claims,
            scope=scope,
            attestor_type="op",
            attestor_id="observer_protocol",
            verification_depth=3,
            reputation_score=1.0
        )
        
        # Sign the attestation
        hash_to_sign = attestation.compute_hash()
        signature = sign_message_secp256k1(
            hash_to_sign.encode(),
            op_signing_key
        )
        
        attestation.proof = AttestationProof(
            signature=signature,
            signer_public_key=op_public_key,
            timestamp=datetime.utcnow().isoformat()
        )
        
        return attestation


def calculate_composite_trust_score(attestations: List[HybridAttestation]) -> Dict[str, Any]:
    """
    Calculate a composite trust score from multiple attestations.
    
    This combines multiple attestations of different trust levels
    into a single trust profile.
    """
    if not attestations:
        return {
            "composite_score": 0.0,
            "max_trust_level": TrustLevel.LEVEL_0,
            "attestation_count": 0,
            "weighted_by_scope": {}
        }
    
    # Calculate weighted average based on trust levels
    total_weight = 0
    weighted_sum = 0
    max_level = TrustLevel.LEVEL_0
    scope_scores: Dict[str, List[float]] = {}
    
    for att in attestations:
        score = att.get_effective_trust_score()
        weight = att.trust_level.value  # Higher trust = more weight
        
        weighted_sum += score * weight
        total_weight += weight
        
        if att.trust_level.value > max_level.value:
            max_level = att.trust_level
        
        # Group by scope
        scope_key = att.scope.scope_type.value
        if scope_key not in scope_scores:
            scope_scores[scope_key] = []
        scope_scores[scope_key].append(score)
    
    composite_score = weighted_sum / total_weight if total_weight > 0 else 0
    
    # Average scores by scope
    weighted_by_scope = {
        scope: sum(scores) / len(scores)
        for scope, scores in scope_scores.items()
    }
    
    return {
        "composite_score": round(composite_score, 4),
        "max_trust_level": {
            "level": max_level.value,
            "name": max_level.name
        },
        "attestation_count": len(attestations),
        "weighted_by_scope": weighted_by_scope
    }


# Convenience functions for common operations

def create_legal_entity_attestation(
    agent_id: str,
    legal_entity_id: str,
    partner_id: str,
    partner_public_key: str,
    partner_private_key: str,
    jurisdiction: Optional[str] = None
) -> HybridAttestation:
    """
    Create a legal entity attestation.
    
    Convenience function for the common case of attesting
    an agent's legal entity wrapper.
    """
    manager = AttestationScopeManager()
    
    claims = {
        "legal_entity_id": legal_entity_id,
        "attestation_type": "legal_entity_verification"
    }
    
    if jurisdiction:
        claims["jurisdiction"] = jurisdiction
    
    return manager.create_partner_attestation(
        agent_id=agent_id,
        partner_id=partner_id,
        claims=claims,
        partner_public_key=partner_public_key,
        partner_private_key=partner_private_key,
        scope_type=AttestationScope.LEGAL_ENTITY
    )


def create_identity_attestation(
    agent_id: str,
    identity_claims: Dict[str, Any],
    op_signing_key: str,
    op_public_key: str
) -> HybridAttestation:
    """
    Create an identity attestation verified by OP.
    
    Highest trust level for identity verification.
    """
    manager = AttestationScopeManager()
    
    return manager.create_op_attestation(
        agent_id=agent_id,
        claims=identity_claims,
        op_signing_key=op_signing_key,
        op_public_key=op_public_key,
        scope_type=AttestationScope.IDENTITY
    )


if __name__ == "__main__":
    # Demo of the attestation scoping system
    print("=" * 60)
    print("Attestation Scoping Demo (Fix #7)")
    print("=" * 60)
    
    # Create attestation manager
    manager = AttestationScopeManager()
    
    # Create a self-attestation
    self_att = manager.create_self_attestation(
        agent_id="agent_123",
        claims={"name": "Test Agent", "version": "1.0"}
    )
    print(f"\nSelf-attestation created:")
    print(f"  Trust level: {self_att.trust_level.name}")
    print(f"  Trust score: {self_att.get_effective_trust_score():.4f}")
    
    # Create a partner attestation
    # Generate test keys
    import sys
    import os
    OP_WORKSPACE_PATH = os.environ.get('OP_WORKSPACE_PATH', 
        os.path.expanduser('~/.openclaw/workspace/observer-protocol'))
    sys.path.insert(0, OP_WORKSPACE_PATH)
    from crypto_verification import sign_message_secp256k1
    
    # Use dummy keys for demo (in production, use real keys)
    demo_partner_private = "deadbeef" * 8  # 256 bits
    demo_partner_public = "03" + "cafebabe" * 8  # Compressed public key
    
    partner_att = manager.create_partner_attestation(
        agent_id="agent_123",
        partner_id="partner_456",
        claims={"legal_entity_id": "CORP-789", "verified": True},
        partner_public_key=demo_partner_public,
        partner_private_key=demo_partner_private
    )
    print(f"\nPartner attestation created:")
    print(f"  Trust level: {partner_att.trust_level.name}")
    print(f"  Trust score: {partner_att.get_effective_trust_score():.4f}")
    print(f"  Has proof: {partner_att.proof is not None}")
    
    # Validate attestations
    validator = AttestationValidator(min_trust_level=TrustLevel.LEVEL_1)
    validator.add_trusted_attestor("partner_456")
    
    result = validator.validate(partner_att)
    print(f"\nValidation result:")
    print(f"  Valid: {result['valid']}")
    print(f"  Trust score: {result['trust_score']:.4f}")
    print(f"  Checks: {result['checks']}")
    
    # Calculate composite score
    composite = calculate_composite_trust_score([self_att, partner_att])
    print(f"\nComposite trust score:")
    print(f"  Score: {composite['composite_score']:.4f}")
    print(f"  Max trust level: {composite['max_trust_level']['name']}")
    print(f"  By scope: {composite['weighted_by_scope']}")
    
    print("\n" + "=" * 60)
    print("Fix #7: Attestation Scoping implementation complete")
    print("=" * 60)
