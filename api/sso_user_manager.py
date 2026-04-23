"""
SSO user management — find or create users, issue sessions.

Matches the existing Web3 onboarding pattern:
  - Same users table, same auth_sessions table
  - Same session cookie shape (enterprise_session)
  - Same 24h cookie / 7d DB session TTL pattern
"""

import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional


SESSION_DB_TTL_DAYS = 7
SESSION_COOKIE_MAX_AGE = 86400  # 24 hours, matching existing Web3 flow


def find_user_by_sso(conn, sso_subject_id: str, org_id: int) -> Optional[dict]:
    """Find an existing user by their SSO subject ID within an org."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, email, name, role, organization_id, is_active,
                   sso_subject_id, sso_provider
            FROM users
            WHERE sso_subject_id = %s AND organization_id = %s AND deleted_at IS NULL
            """,
            (sso_subject_id, org_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "email": row[1],
            "name": row[2],
            "role": row[3],
            "organization_id": row[4],
            "is_active": row[5],
            "sso_subject_id": row[6],
            "sso_provider": row[7],
        }
    finally:
        cursor.close()


def create_sso_user(
    conn,
    email: str,
    name: str,
    org_id: int,
    role: str,
    sso_subject_id: str,
    sso_provider: str,
    sso_org_idp_config_id: int,
) -> dict:
    """
    Create a new user provisioned via SSO.

    Args:
        email: User's email from SAML assertion.
        name: Display name from SAML assertion (falls back to email prefix).
        org_id: Organization ID.
        role: Role to assign (from org_idp_config.default_role).
        sso_subject_id: NameID from SAML assertion.
        sso_provider: 'saml' for phase 1.
        sso_org_idp_config_id: FK to org_idp_config.id.

    Returns:
        User dict with id, email, role, etc.
    """
    display_name = name or email.split("@")[0]

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO users (email, name, organization_id, role,
                               sso_subject_id, sso_provider, sso_org_idp_config_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (email, display_name, org_id, role,
             sso_subject_id, sso_provider, sso_org_idp_config_id),
        )
        user_id = cursor.fetchone()[0]
        conn.commit()

        return {
            "id": str(user_id),
            "email": email,
            "name": display_name,
            "role": role,
            "organization_id": org_id,
            "sso_subject_id": sso_subject_id,
            "sso_provider": sso_provider,
            "is_new": True,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def create_session(conn, user_id: str, ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> dict:
    """
    Create a session in auth_sessions. Returns the raw session token
    (not the hash — the hash is stored in the DB, the raw token goes in the cookie).

    Matches existing Web3 flow exactly.
    """
    session_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(session_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DB_TTL_DAYS)

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO auth_sessions (user_id, token_hash, expires_at, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, token_hash, expires_at, ip_address, user_agent),
        )

        # Update last_login_at on user
        cursor.execute(
            "UPDATE users SET last_login_at = NOW() WHERE id = %s",
            (user_id,),
        )

        conn.commit()

        return {
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "cookie_max_age": SESSION_COOKIE_MAX_AGE,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def validate_invitation_token(conn, token: str) -> Optional[dict]:
    """
    Validate an invitation token and return the invitation details.
    Checks that the token exists, hasn't expired, and hasn't been used.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT i.organization_id, i.email, i.role, i.expires_at,
                   o.org_name, o.domain
            FROM user_invitations i
            JOIN organizations o ON i.organization_id = o.id
            WHERE i.token = %s AND i.used_at IS NULL AND i.expires_at > NOW()
            """,
            (token,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "organization_id": row[0],
            "email": row[1],
            "role": row[2],
            "expires_at": row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3]),
            "org_name": row[4],
            "domain": row[5],
        }
    finally:
        cursor.close()


def mark_invitation_used(conn, token: str, user_id: str) -> None:
    """Mark an invitation token as used after successful onboarding."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE user_invitations SET used_at = NOW() WHERE token = %s",
            (token,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def get_org_info(conn, org_id: int) -> Optional[dict]:
    """Fetch org name and domain for cookie/response."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, org_name, domain FROM organizations WHERE id = %s",
            (org_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"id": row[0], "org_name": row[1], "domain": row[2]}
    finally:
        cursor.close()
