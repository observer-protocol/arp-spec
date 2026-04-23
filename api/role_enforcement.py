"""
Role enforcement for enterprise API endpoints.

Spec 3.8.1 — closes the gap documented in ROLE_ENFORCEMENT_AUDIT.md where
validate_enterprise_session() extracts role but no handler checks it.

Three-level hierarchy:
  viewer (0) — read-only access to org data
  operator (1) — routine operations (register agents, submit transactions)
  admin (2) — destructive/irreversible actions (revoke, rotate keys, approve delegations)

'auditor' is treated as equivalent to 'viewer' (legacy DB default).
'platform-admin' is treated as >= admin (superset).

Usage:
  from role_enforcement import require_role

  @router.post("/some-endpoint")
  async def some_endpoint(request: Request):
      user_id, org_id, email, role = require_role(request, "operator")
      ...
"""

from fastapi import HTTPException, Request
from typing import Callable, Tuple


# Role hierarchy: lower number = less privilege
ROLE_HIERARCHY = {
    "viewer": 0,
    "auditor": 0,       # Legacy DB default, equivalent to viewer
    "operator": 1,
    "admin": 2,
    "platform-admin": 3,  # Superset of admin
}


def require_role(
    session_tuple: tuple,
    minimum_role: str,
) -> tuple:
    """
    Check that the session's role meets the minimum required level.

    Args:
        session_tuple: The (user_id, org_id, email, role) tuple from
            validate_enterprise_session().
        minimum_role: The minimum role required ('viewer', 'operator', 'admin').

    Returns:
        The session_tuple unchanged (pass-through for convenience).

    Raises:
        HTTPException 403 if the role is insufficient.
    """
    user_id, org_id, email, role = session_tuple
    user_level = ROLE_HIERARCHY.get(role.lower() if role else "", -1)
    required_level = ROLE_HIERARCHY.get(minimum_role.lower(), 99)

    if user_level < required_level:
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions: requires {minimum_role} role or higher",
        )

    return session_tuple


def check_role(role: str, minimum_role: str) -> bool:
    """
    Pure check without raising. For use in conditional logic.

    Returns True if role >= minimum_role in the hierarchy.
    """
    user_level = ROLE_HIERARCHY.get(role.lower() if role else "", -1)
    required_level = ROLE_HIERARCHY.get(minimum_role.lower(), 99)
    return user_level >= required_level
