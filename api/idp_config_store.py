"""
Data access layer for org_idp_config table.

Manages per-org SAML IdP configurations. One IdP per org in phase 1.
"""

import json
from typing import Optional


class IdPConfigNotFoundError(Exception):
    pass


def create_or_update_idp_config(
    conn,
    org_id: int,
    idp_entity_id: str,
    idp_sso_url: str,
    idp_x509_cert: str,
    sp_entity_id: str,
    acs_url: str,
    attribute_mapping: Optional[dict] = None,
    default_role: str = "viewer",
    created_by: Optional[str] = None,
) -> dict:
    """Create or update an org's IdP config. Upsert on org_id."""
    if attribute_mapping is None:
        attribute_mapping = {"email": "email", "display_name": "DisplayName", "role": None}

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM org_idp_config WHERE org_id = %s",
            (org_id,),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE org_idp_config SET
                    idp_entity_id = %s, idp_sso_url = %s, idp_x509_cert = %s,
                    sp_entity_id = %s, acs_url = %s, attribute_mapping = %s,
                    default_role = %s, updated_at = NOW(), is_active = TRUE
                WHERE org_id = %s
                """,
                (
                    idp_entity_id, idp_sso_url, idp_x509_cert,
                    sp_entity_id, acs_url, json.dumps(attribute_mapping),
                    default_role, org_id,
                ),
            )
            config_id = existing[0]
        else:
            cursor.execute(
                """
                INSERT INTO org_idp_config
                    (org_id, provider, idp_entity_id, idp_sso_url, idp_x509_cert,
                     sp_entity_id, acs_url, attribute_mapping, default_role, created_by)
                VALUES (%s, 'saml', %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    org_id, idp_entity_id, idp_sso_url, idp_x509_cert,
                    sp_entity_id, acs_url, json.dumps(attribute_mapping),
                    default_role, created_by,
                ),
            )
            # Fetch the new ID
            cursor.execute(
                "SELECT id FROM org_idp_config WHERE org_id = %s",
                (org_id,),
            )
            config_id = cursor.fetchone()[0]

        conn.commit()
        return get_idp_config(conn, org_id)

    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def get_idp_config(conn, org_id: int) -> Optional[dict]:
    """Fetch an org's active IdP config."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, org_id, provider, idp_entity_id, idp_sso_url,
                   idp_x509_cert, sp_entity_id, acs_url,
                   attribute_mapping, default_role, is_active,
                   created_at, updated_at
            FROM org_idp_config
            WHERE org_id = %s AND is_active = TRUE
            """,
            (org_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "org_id": row[1],
            "provider": row[2],
            "idp_entity_id": row[3],
            "idp_sso_url": row[4],
            "idp_x509_cert": row[5],
            "sp_entity_id": row[6],
            "acs_url": row[7],
            "attribute_mapping": row[8] if isinstance(row[8], dict) else json.loads(row[8]),
            "default_role": row[9],
            "is_active": row[10],
            "created_at": row[11].isoformat() if hasattr(row[11], "isoformat") else str(row[11]),
            "updated_at": row[12].isoformat() if hasattr(row[12], "isoformat") else str(row[12]),
        }
    finally:
        cursor.close()


def get_idp_config_by_domain(conn, domain: str) -> Optional[dict]:
    """Look up IdP config by org domain (for login-by-email flow)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT c.id, c.org_id, c.provider, c.idp_entity_id, c.idp_sso_url,
                   c.idp_x509_cert, c.sp_entity_id, c.acs_url,
                   c.attribute_mapping, c.default_role, c.is_active
            FROM org_idp_config c
            JOIN organizations o ON c.org_id = o.id
            WHERE o.domain = %s AND c.is_active = TRUE
            """,
            (domain,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row[0], "org_id": row[1], "provider": row[2],
            "idp_entity_id": row[3], "idp_sso_url": row[4],
            "idp_x509_cert": row[5], "sp_entity_id": row[6],
            "acs_url": row[7],
            "attribute_mapping": row[8] if isinstance(row[8], dict) else json.loads(row[8]),
            "default_role": row[9], "is_active": row[10],
        }
    finally:
        cursor.close()


def delete_idp_config(conn, org_id: int) -> bool:
    """Soft-delete: set is_active = FALSE."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE org_idp_config SET is_active = FALSE, updated_at = NOW() WHERE org_id = %s AND is_active = TRUE",
            (org_id,),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
