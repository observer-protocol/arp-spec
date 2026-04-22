"""
Delegation Credential Verification Module
Implements Spec 3.2 - Recursive DID-to-DID Delegation Verification

Key features:
- Single-edge verification (signature, schema, validity period)
- Graph traversal with cycle detection
- Scope attenuation enforcement (per §5.3)
- Offline verification support via caching
"""

import json
import base58
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List, Set
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

# Import from existing verification infrastructure
from vc_verification import (
    fetch_schema,
    validate_credential_against_schema,
    check_validity_period,
    resolve_issuer_did,
    extract_verification_method,
    verify_ed25519_signature_2020,
    _SCHEMA_CACHE,
    _DID_CACHE
)
from did_resolver import resolve_did, extract_public_key_bytes


# Delegation schema URL
DELEGATION_SCHEMA_URL = "https://observerprotocol.org/schemas/delegation/v1.json"


def verify_delegation_edge(credential: Dict, use_cache: bool = True) -> Dict[str, Any]:
    """
    Verify a single delegation credential edge.
    
    Implements Spec 3.2 §5.1:
    1. Resolve issuer DID
    2. Extract verificationMethod from proof
    3. Verify Ed25519 signature
    4. Validate against delegation schema
    5. Check validFrom <= now < validUntil
    
    Args:
        credential: The DelegationCredential VC to verify
        use_cache: Whether to use cached schemas and DID documents
        
    Returns:
        {
            "verified": bool,
            "checks": {
                "signature": "pass"|"fail",
                "schema": "pass"|"fail", 
                "validity_period": "pass"|"fail",
                "issuer_did_resolvable": "pass"|"fail"
            },
            "issuer_did": str,
            "subject_did": str,
            "credential_id": str,
            "error": str (optional)
        }
    """
    result = {
        "verified": False,
        "checks": {
            "signature": "fail",
            "schema": "fail",
            "validity_period": "fail",
            "issuer_did_resolvable": "fail"
        },
        "issuer_did": None,
        "subject_did": None,
        "credential_id": None
    }
    
    # Extract basic fields
    credential_id = credential.get('id')
    result['credential_id'] = credential_id
    
    issuer_did = credential.get('issuer')
    if isinstance(issuer_did, dict):
        issuer_did = issuer_did.get('id')
    result['issuer_did'] = issuer_did
    
    subject = credential.get('credentialSubject', {})
    result['subject_did'] = subject.get('id') if isinstance(subject, dict) else None
    
    # 1. Resolve Issuer DID
    did_doc, error = resolve_issuer_did(issuer_did, use_cache=use_cache)
    if error:
        result['error'] = error
        return result
    
    result['checks']['issuer_did_resolvable'] = "pass"
    
    # 2. Validate against schema
    schema_url = credential.get('credentialSchema', {}).get('id')
    if schema_url:
        schema = fetch_schema(schema_url) if use_cache else _fetch_schema_no_cache(schema_url)
        if schema:
            schema_valid, schema_error = validate_credential_against_schema(credential, schema)
            if schema_valid:
                result['checks']['schema'] = "pass"
            else:
                result['error'] = schema_error
                return result
    else:
        result['error'] = "Missing credentialSchema"
        return result
    
    # 3. Check validity period
    valid_from = credential.get('validFrom')
    valid_until = credential.get('validUntil')
    
    if valid_from and valid_until:
        period_valid, period_error = check_validity_period(valid_from, valid_until)
        if period_valid:
            result['checks']['validity_period'] = "pass"
        else:
            result['error'] = period_error
            return result
    else:
        result['error'] = "Missing validFrom or validUntil"
        return result
    
    # 4. Verify signature
    proof = credential.get('proof', {})
    if not proof:
        result['error'] = "Missing proof in credential"
        return result
    
    verification_method_id = proof.get('verificationMethod')
    if not verification_method_id:
        result['error'] = "Missing verificationMethod in proof"
        return result
    
    # Extract public key bytes
    try:
        public_key_bytes = extract_public_key_bytes(did_doc, verification_method_id)
    except Exception as e:
        result['error'] = f"Failed to extract public key: {str(e)}"
        return result
    
    # Verify the signature
    credential_without_proof = {k: v for k, v in credential.items() if k != 'proof'}
    
    sig_valid, sig_error = verify_ed25519_signature_2020(
        credential_without_proof,
        proof,
        public_key_bytes
    )
    
    if sig_valid:
        result['checks']['signature'] = "pass"
    else:
        result['error'] = sig_error or "Signature verification failed"
        return result
    
    # All checks passed
    result['verified'] = True
    return result


def _fetch_schema_no_cache(schema_url: str) -> Optional[Dict]:
    """Fetch schema without using cache (for offline verification)."""
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(schema_url)
            response.raise_for_status()
            return response.json()
    except Exception:
        return None


def _fetch_credential_from_url(url: str, timeout: int = 10) -> Optional[Dict]:
    """Fetch a credential from a URL."""
    # Try memory cache first (for offline mode)
    from vc_verification import get_cached_schema, _SCHEMA_CACHE
    
    # Check if we have this credential cached
    if url in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[url]
    
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            credential = response.json()
            # Cache for offline use
            _SCHEMA_CACHE[url] = credential
            return credential
    except Exception as e:
        print(f"Failed to fetch credential from {url}: {e}")
        return None


def _is_list_subset(child_list: Optional[List], parent_list: Optional[List]) -> bool:
    """Check if child_list is a subset of parent_list."""
    if child_list is None:
        return True  # Absence means inherit parent's list
    if parent_list is None:
        return len(child_list) == 0  # Parent has no restrictions, child must have none
    return set(child_list).issubset(set(parent_list))


def _is_numeric_ceiling_valid(child: Optional[Dict], parent: Optional[Dict]) -> Tuple[bool, str]:
    """
    Check if child's numeric ceiling is valid against parent's.
    Per Spec 3.2 §5.3: child's amount MUST be <= parent's amount
    """
    if child is None:
        return True, ""  # Absence means inherit
    if parent is None:
        return False, "Child has ceiling but parent has none"
    
    try:
        child_amount = float(child.get('amount', '0'))
        parent_amount = float(parent.get('amount', '0'))
    except (ValueError, TypeError) as e:
        return False, f"Invalid numeric format: {e}"
    
    # Currency must match
    child_currency = child.get('currency')
    parent_currency = parent.get('currency')
    if child_currency != parent_currency:
        return False, f"Currency mismatch: child={child_currency}, parent={parent_currency}"
    
    if child_amount > parent_amount:
        return False, f"Child amount {child_amount} exceeds parent amount {parent_amount}"
    
    return True, ""


def _is_cumulative_ceiling_valid(child: Optional[Dict], parent: Optional[Dict]) -> Tuple[bool, str]:
    """
    Check if child's cumulative ceiling is valid against parent's.
    Per Spec 3.2 §5.3: child's period MUST be <= parent's period
    """
    if child is None:
        return True, ""
    if parent is None:
        return False, "Child has cumulative ceiling but parent has none"
    
    # First check amount and currency
    amount_valid, amount_error = _is_numeric_ceiling_valid(child, parent)
    if not amount_valid:
        return False, amount_error
    
    # Check period - child period must be <= parent period (shorter is more restrictive)
    child_period = child.get('period', 'P0D')
    parent_period = parent.get('period', 'P0D')
    
    try:
        child_days = _parse_iso_duration(child_period)
        parent_days = _parse_iso_duration(parent_period)
    except ValueError as e:
        return False, f"Invalid duration format: {e}"
    
    if child_days > parent_days:
        return False, f"Child period {child_period} exceeds parent period {parent_period}"
    
    return True, ""


def _parse_iso_duration(duration: str) -> int:
    """
    Parse ISO 8601 duration to days (approximate for months/years).
    Returns total days.
    """
    if not duration.startswith('P'):
        raise ValueError(f"Invalid ISO 8601 duration: {duration}")
    
    duration = duration[1:]  # Remove 'P'
    days = 0
    
    # Extract number and unit
    import re
    matches = re.findall(r'(\d+)([YMD])', duration)
    
    for num, unit in matches:
        num = int(num)
        if unit == 'Y':
            days += num * 365  # Approximate
        elif unit == 'M':
            days += num * 30   # Approximate
        elif unit == 'D':
            days += num
    
    return days


def _is_geographic_restriction_valid(child: Optional[Dict], parent: Optional[Dict]) -> Tuple[bool, str]:
    """
    Check geographic restrictions.
    Per Spec 3.2 §5.3:
    - child's allow-list MUST be subset of parent's allow-list
    - child's deny-list MUST be superset of parent's deny-list
    """
    if child is None:
        return True, ""
    if parent is None:
        # Parent has no restrictions, child can have any
        return True, ""
    
    child_allowed = child.get('allowed', [])
    parent_allowed = parent.get('allowed', [])
    child_disallowed = child.get('disallowed', [])
    parent_disallowed = parent.get('disallowed', [])
    
    # If parent has allow-list, child's must be subset
    if parent_allowed:
        if child_allowed:
            if not set(child_allowed).issubset(set(parent_allowed)):
                return False, f"Child allowed {child_allowed} not subset of parent allowed {parent_allowed}"
    
    # Child's disallowed must be superset of parent's disallowed
    if parent_disallowed:
        if not set(parent_disallowed).issubset(set(child_disallowed or [])):
            return False, f"Parent disallowed {parent_disallowed} not subset of child disallowed {child_disallowed}"
    
    return True, ""


def _is_boolean_permission_valid(child_value: bool, parent_value: bool, permission_name: str) -> Tuple[bool, str]:
    """
    Check boolean permission.
    Per Spec 3.2 §5.3: child's true requires parent's true
    """
    if child_value and not parent_value:
        return False, f"Child has {permission_name}=true but parent has false"
    return True, ""


def check_action_scope_attenuation(child_scope: Dict, parent_scope: Dict) -> Tuple[bool, str]:
    """
    Check if child's action scope is properly attenuated from parent's.
    Implements Spec 3.2 §5.3 attenuation rules.
    """
    # allowed_rails: child's list ⊆ parent's list
    if not _is_list_subset(
        child_scope.get('allowed_rails'),
        parent_scope.get('allowed_rails')
    ):
        return False, "Child allowed_rails not subset of parent"
    
    # allowed_counterparty_types: child's list ⊆ parent's list
    if not _is_list_subset(
        child_scope.get('allowed_counterparty_types'),
        parent_scope.get('allowed_counterparty_types')
    ):
        return False, "Child allowed_counterparty_types not subset of parent"
    
    # allowed_merchant_categories: child's list ⊆ parent's list
    if not _is_list_subset(
        child_scope.get('allowed_merchant_categories'),
        parent_scope.get('allowed_merchant_categories')
    ):
        return False, "Child allowed_merchant_categories not subset of parent"
    
    # per_transaction_ceiling: child's amount <= parent's amount
    valid, error = _is_numeric_ceiling_valid(
        child_scope.get('per_transaction_ceiling'),
        parent_scope.get('per_transaction_ceiling')
    )
    if not valid:
        return False, f"per_transaction_ceiling violation: {error}"
    
    # cumulative_ceiling: child's amount <= parent's amount, child's period <= parent's period
    valid, error = _is_cumulative_ceiling_valid(
        child_scope.get('cumulative_ceiling'),
        parent_scope.get('cumulative_ceiling')
    )
    if not valid:
        return False, f"cumulative_ceiling violation: {error}"
    
    # geographic_restriction
    valid, error = _is_geographic_restriction_valid(
        child_scope.get('geographic_restriction'),
        parent_scope.get('geographic_restriction')
    )
    if not valid:
        return False, f"geographic_restriction violation: {error}"
    
    return True, ""


def check_delegation_scope_attenuation(child_scope: Dict, parent_scope: Dict) -> Tuple[bool, str]:
    """
    Check if child's delegation scope is properly attenuated from parent's.
    """
    # may_delegate_further: child's true requires parent's true
    valid, error = _is_boolean_permission_valid(
        child_scope.get('may_delegate_further', False),
        parent_scope.get('may_delegate_further', False),
        "may_delegate_further"
    )
    if not valid:
        return False, error
    
    # may_delegate_delegation_authority: child's true requires parent's true
    valid, error = _is_boolean_permission_valid(
        child_scope.get('may_delegate_delegation_authority', False),
        parent_scope.get('may_delegate_delegation_authority', False),
        "may_delegate_delegation_authority"
    )
    if not valid:
        return False, error
    
    # max_child_action_scope: must be attenuated from parent's max_child_action_scope
    child_max = child_scope.get('max_child_action_scope', {})
    parent_max = parent_scope.get('max_child_action_scope', {})
    
    if child_max or parent_max:
        valid, error = check_action_scope_attenuation(child_max, parent_max)
        if not valid:
            return False, f"max_child_action_scope violation: {error}"
    
    # allowed_child_subject_types: child's list ⊆ parent's list
    if not _is_list_subset(
        child_scope.get('allowed_child_subject_types'),
        parent_scope.get('allowed_child_subject_types')
    ):
        return False, "Child allowed_child_subject_types not subset of parent"
    
    return True, ""


def check_temporal_consistency(child_credential: Dict, parent_credential: Dict) -> Tuple[bool, str]:
    """
    Check temporal consistency between child and parent.
    Per Spec 3.2 §5.2: child's validUntil MUST be ≤ parent's validUntil
    """
    child_valid_until = child_credential.get('validUntil')
    parent_valid_until = parent_credential.get('validUntil')
    
    if not child_valid_until or not parent_valid_until:
        return True, ""  # No temporal constraint if missing
    
    try:
        child_dt = datetime.fromisoformat(child_valid_until.replace('Z', '+00:00'))
        parent_dt = datetime.fromisoformat(parent_valid_until.replace('Z', '+00:00'))
    except Exception as e:
        return False, f"Invalid date format: {e}"
    
    if child_dt > parent_dt:
        return False, f"Child validUntil {child_valid_until} > parent validUntil {parent_valid_until}"
    
    return True, ""


async def verify_delegation_chain(
    leaf_credential: Dict,
    max_depth: int = 10,
    use_cache: bool = True,
    _visited_dids: Optional[Set[str]] = None,
    _current_depth: int = 0
) -> Dict[str, Any]:
    """
    Walk delegation chain from leaf to root, verifying every edge.
    
    Implements Spec 3.2 §5.2 and §5.3:
    1. Verify leaf edge (single-edge verification)
    2. If parentDelegationId exists:
       a. Fetch parent credential
       b. Recursively verify parent
       c. Check attenuation rules
       d. Check delegation permission
       e. Check subject type constraints
       f. Check temporal: child's validUntil ≤ parent's validUntil
    3. Detect cycles (track visited issuer DIDs)
    4. Compute effective_action_scope by intersecting all scopes in chain
    
    Args:
        leaf_credential: The leaf delegation credential to verify
        max_depth: Maximum chain depth to prevent infinite loops
        use_cache: Whether to use cached schemas and DIDs
        _visited_dids: Internal set for cycle detection
        _current_depth: Internal depth counter
        
    Returns:
        {
            "verified": bool,
            "checks": {
                "signature": "pass"|"fail",
                "schema": "pass"|"fail",
                "validity_period": "pass"|"fail",
                "issuer_did_resolvable": "pass"|"fail",
                "attenuation": "pass"|"fail",
                "no_cycles": "pass"|"fail",
                "chain_complete": "pass"|"fail"
            },
            "chain": [...],
            "effective_action_scope": {...},
            "error": str (optional)
        }
    """
    result = {
        "verified": False,
        "checks": {
            "signature": "fail",
            "schema": "fail",
            "validity_period": "fail",
            "issuer_did_resolvable": "fail",
            "attenuation": "fail",
            "no_cycles": "fail",
            "chain_complete": "fail"
        },
        "chain": [],
        "effective_action_scope": None
    }
    
    # Initialize visited set for cycle detection
    if _visited_dids is None:
        _visited_dids = set()
    
    # Check max depth
    if _current_depth >= max_depth:
        result['error'] = f"Max chain depth ({max_depth}) exceeded"
        return result
    
    # 1. Verify the leaf edge
    edge_result = verify_delegation_edge(leaf_credential, use_cache=use_cache)
    
    # Copy basic checks from edge verification
    result['checks']['signature'] = edge_result['checks']['signature']
    result['checks']['schema'] = edge_result['checks']['schema']
    result['checks']['validity_period'] = edge_result['checks']['validity_period']
    result['checks']['issuer_did_resolvable'] = edge_result['checks']['issuer_did_resolvable']
    
    if not edge_result['verified']:
        result['error'] = edge_result.get('error', 'Edge verification failed')
        return result
    
    # Add this edge to chain
    issuer_did = edge_result['issuer_did']
    subject_did = edge_result['subject_did']
    credential_id = edge_result['credential_id']
    
    result['chain'].append({
        "credential_id": credential_id,
        "issuer_did": issuer_did,
        "subject_did": subject_did,
        "depth": _current_depth
    })
    
    # Cycle detection: check if we've seen this issuer before
    if issuer_did in _visited_dids:
        result['error'] = f"Cycle detected: issuer {issuer_did} already in chain"
        return result
    
    result['checks']['no_cycles'] = "pass"
    _visited_dids.add(issuer_did)
    
    # Get credential subject for attenuation checks
    subject = leaf_credential.get('credentialSubject', {})
    child_action_scope = subject.get('actionScope', {})
    child_delegation_scope = subject.get('delegationScope', {})
    parent_delegation_id = subject.get('parentDelegationId')
    
    # Start with child's action scope as effective scope
    effective_scope = json.loads(json.dumps(child_action_scope))  # Deep copy
    
    # 2. If parent exists, recursively verify
    if parent_delegation_id:
        # Fetch parent credential
        parent_credential = _fetch_credential_from_url(parent_delegation_id)
        
        if not parent_credential:
            result['error'] = f"Failed to fetch parent credential from {parent_delegation_id}"
            return result
        
        # Verify parent chain recursively
        parent_result = await verify_delegation_chain(
            parent_credential,
            max_depth=max_depth,
            use_cache=use_cache,
            _visited_dids=_visited_dids,
            _current_depth=_current_depth + 1
        )
        
        if not parent_result['verified']:
            result['error'] = f"Parent chain verification failed: {parent_result.get('error')}"
            return result
        
        # Extend chain with parent's chain
        result['chain'].extend(parent_result['chain'])
        
        # Get parent's effective scope and delegation scope
        parent_subject = parent_credential.get('credentialSubject', {})
        parent_action_scope = parent_subject.get('actionScope', {})
        parent_delegation_scope = parent_subject.get('delegationScope', {})
        
        # 2c. Check action scope attenuation
        valid, error = check_action_scope_attenuation(child_action_scope, parent_action_scope)
        if not valid:
            result['error'] = f"Action scope attenuation violated: {error}"
            return result
        
        # 2d. Check delegation permission
        # Parent's may_delegate_further must be true
        if not parent_delegation_scope.get('may_delegate_further', False):
            result['error'] = "Parent has may_delegate_further=false but child delegation exists"
            return result
        
        # If child may delegate further, parent's may_delegate_delegation_authority must be true
        if child_delegation_scope.get('may_delegate_further', False):
            if not parent_delegation_scope.get('may_delegate_delegation_authority', False):
                result['error'] = "Child has may_delegate_further=true but parent has may_delegate_delegation_authority=false"
                return result
        
        # 2e. Check subject type constraints
        child_subject_type = None  # TODO: Determine subject type from DID or context
        allowed_child_types = parent_delegation_scope.get('allowed_child_subject_types', [])
        if allowed_child_types and child_subject_type:
            if child_subject_type not in allowed_child_types:
                result['error'] = f"Subject type {child_subject_type} not in allowed_child_subject_types"
                return result
        
        # 2f. Check temporal consistency
        valid, error = check_temporal_consistency(leaf_credential, parent_credential)
        if not valid:
            result['error'] = f"Temporal consistency violated: {error}"
            return result
        
        # Compute effective scope by intersecting with parent's effective scope
        parent_effective = parent_result.get('effective_action_scope', {})
        if parent_effective:
            effective_scope = _intersect_action_scopes(effective_scope, parent_effective)
    else:
        # No parent - this is a root delegation
        result['checks']['chain_complete'] = "pass"
    
    result['checks']['attenuation'] = "pass"
    result['checks']['chain_complete'] = "pass"
    result['effective_action_scope'] = effective_scope
    result['verified'] = True
    
    return result


def _intersect_action_scopes(child_scope: Dict, parent_scope: Dict) -> Dict:
    """
    Compute the effective action scope by intersecting child and parent scopes.
    The effective scope is the most restrictive of the two.
    """
    effective = {}
    
    # allowed_rails: intersection of both lists
    child_rails = child_scope.get('allowed_rails', [])
    parent_rails = parent_scope.get('allowed_rails', [])
    if child_rails and parent_rails:
        effective['allowed_rails'] = list(set(child_rails) & set(parent_rails))
    elif child_rails:
        effective['allowed_rails'] = child_rails
    elif parent_rails:
        effective['allowed_rails'] = parent_rails
    
    # allowed_counterparty_types: intersection
    child_types = child_scope.get('allowed_counterparty_types', [])
    parent_types = parent_scope.get('allowed_counterparty_types', [])
    if child_types and parent_types:
        effective['allowed_counterparty_types'] = list(set(child_types) & set(parent_types))
    elif child_types:
        effective['allowed_counterparty_types'] = child_types
    elif parent_types:
        effective['allowed_counterparty_types'] = parent_types
    
    # per_transaction_ceiling: minimum of both
    child_ceiling = child_scope.get('per_transaction_ceiling')
    parent_ceiling = parent_scope.get('per_transaction_ceiling')
    if child_ceiling and parent_ceiling:
        try:
            child_amount = float(child_ceiling['amount'])
            parent_amount = float(parent_ceiling['amount'])
            effective['per_transaction_ceiling'] = {
                'amount': str(min(child_amount, parent_amount)),
                'currency': child_ceiling['currency']  # Already validated they match
            }
        except (ValueError, KeyError):
            pass
    elif child_ceiling:
        effective['per_transaction_ceiling'] = child_ceiling
    elif parent_ceiling:
        effective['per_transaction_ceiling'] = parent_ceiling
    
    # cumulative_ceiling: minimum amount, minimum period
    child_cumulative = child_scope.get('cumulative_ceiling')
    parent_cumulative = parent_scope.get('cumulative_ceiling')
    if child_cumulative and parent_cumulative:
        try:
            child_amount = float(child_cumulative['amount'])
            parent_amount = float(parent_cumulative['amount'])
            effective['cumulative_ceiling'] = {
                'amount': str(min(child_amount, parent_amount)),
                'currency': child_cumulative['currency'],
                'period': _shorter_duration(child_cumulative['period'], parent_cumulative['period'])
            }
        except (ValueError, KeyError):
            pass
    elif child_cumulative:
        effective['cumulative_ceiling'] = child_cumulative
    elif parent_cumulative:
        effective['cumulative_ceiling'] = parent_cumulative
    
    # geographic_restriction: intersection of allowed, union of disallowed
    child_geo = child_scope.get('geographic_restriction')
    parent_geo = parent_scope.get('geographic_restriction')
    if child_geo or parent_geo:
        effective_geo = {}
        
        child_allowed = set(child_geo.get('allowed', [])) if child_geo else set()
        parent_allowed = set(parent_geo.get('allowed', [])) if parent_geo else set()
        if child_allowed and parent_allowed:
            effective_geo['allowed'] = list(child_allowed & parent_allowed)
        elif child_allowed:
            effective_geo['allowed'] = list(child_allowed)
        elif parent_allowed:
            effective_geo['allowed'] = list(parent_allowed)
        
        child_disallowed = set(child_geo.get('disallowed', [])) if child_geo else set()
        parent_disallowed = set(parent_geo.get('disallowed', [])) if parent_geo else set()
        if child_disallowed or parent_disallowed:
            effective_geo['disallowed'] = list(child_disallowed | parent_disallowed)
        
        if effective_geo:
            effective['geographic_restriction'] = effective_geo
    
    # allowed_merchant_categories: intersection
    child_merchants = child_scope.get('allowed_merchant_categories', [])
    parent_merchants = parent_scope.get('allowed_merchant_categories', [])
    if child_merchants and parent_merchants:
        effective['allowed_merchant_categories'] = list(set(child_merchants) & set(parent_merchants))
    elif child_merchants:
        effective['allowed_merchant_categories'] = child_merchants
    elif parent_merchants:
        effective['allowed_merchant_categories'] = parent_merchants
    
    return effective


def _shorter_duration(duration1: str, duration2: str) -> str:
    """Return the shorter (more restrictive) of two ISO 8601 durations."""
    try:
        days1 = _parse_iso_duration(duration1)
        days2 = _parse_iso_duration(duration2)
        return duration1 if days1 <= days2 else duration2
    except:
        return duration1  # Default to first if parsing fails


async def get_delegation_chain_from_db(leaf_credential_id: str) -> List[Dict]:
    """
    Use recursive CTE to walk chain in database.
    Returns list of credential records from leaf to root.
    
    Spec 3.2 §8.2
    """
    import os
    import psycopg2
    
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        # Try fallback
        database_url = "postgresql://postgres:postgres@localhost:5432/agentic_terminal_db"
    
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            WITH RECURSIVE delegation_chain AS (
                SELECT 
                    credential_id, 
                    issuer_did, 
                    subject_did, 
                    parent_delegation_id, 
                    credential_jsonld,
                    1 AS depth
                FROM delegation_credentials
                WHERE credential_id = %s
                
                UNION ALL
                
                SELECT 
                    d.credential_id, 
                    d.issuer_did, 
                    d.subject_did, 
                    d.parent_delegation_id,
                    d.credential_jsonld,
                    dc.depth + 1
                FROM delegation_credentials d
                JOIN delegation_chain dc ON d.credential_id = dc.parent_delegation_id
                WHERE dc.depth < 10  -- Prevent infinite recursion
            )
            SELECT * FROM delegation_chain ORDER BY depth;
        """, (leaf_credential_id,))
        
        rows = cursor.fetchall()
        chain = []
        for row in rows:
            chain.append({
                "credential_id": row[0],
                "issuer_did": row[1],
                "subject_did": row[2],
                "parent_delegation_id": row[3],
                "credential_jsonld": row[4],
                "depth": row[5]
            })
        return chain
    finally:
        cursor.close()
        conn.close()
