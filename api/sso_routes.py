"""
Spec 3.8 — SSO API endpoints.

6 endpoints:

  POST /api/v1/auth/sso/saml/login          — initiate SSO flow (public)
  POST /api/v1/auth/sso/saml/callback        — SAML ACS (public, IdP posts here)
  GET  /api/v1/auth/sso/saml/metadata        — SP metadata XML (public)
  POST /api/v1/admin/orgs/{org_id}/idp-config — create/update IdP config (admin)
  GET  /api/v1/admin/orgs/{org_id}/idp-config — get IdP config (admin)
  DELETE /api/v1/admin/orgs/{org_id}/idp-config — disable SSO for org (admin)
"""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Form, Query
from fastapi.responses import JSONResponse, Response, RedirectResponse

from saml_handler import (
    generate_authn_request,
    verify_saml_response,
    generate_sp_metadata,
    SAMLVerificationError,
)
from sso_user_manager import (
    find_user_by_sso,
    create_sso_user,
    create_session,
    validate_invitation_token,
    mark_invitation_used,
    get_org_info,
    SESSION_COOKIE_MAX_AGE,
)
from idp_config_store import (
    create_or_update_idp_config,
    get_idp_config,
    get_idp_config_by_domain,
    delete_idp_config,
    IdPConfigNotFoundError,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

_get_db_connection = None
_validate_admin_session = None  # Callable(request) -> (user_id, org_id, email, role)
_dashboard_url = "https://app.agenticterminal.io"
_cookie_domain = ".agenticterminal.io"


def configure(
    get_db_connection_fn,
    validate_admin_session_fn,
    dashboard_url: str = "https://app.agenticterminal.io",
    cookie_domain: str = ".agenticterminal.io",
):
    global _get_db_connection, _validate_admin_session, _dashboard_url, _cookie_domain
    _get_db_connection = get_db_connection_fn
    _validate_admin_session = validate_admin_session_fn
    _dashboard_url = dashboard_url
    _cookie_domain = cookie_domain


def _require_configured():
    if _get_db_connection is None:
        raise RuntimeError("SSO routes not configured. Call configure() at startup.")


def _require_platform_admin(request: Request) -> tuple:
    """Validate the caller is a platform admin. Returns (user_id, org_id, email, role)."""
    if _validate_admin_session is None:
        raise RuntimeError("Admin session validator not configured")
    result = _validate_admin_session(request)
    user_id, org_id, email, role = result
    if role != "platform-admin":
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return result


def _log_sso_event(conn, event_type: str, details: dict):
    """Log an SSO auth event. Matches existing audit event pattern."""
    # Phase 1: log to stdout. Phase 2: write to audit table.
    import sys
    print(f"[SSO] {event_type}: {json.dumps(details)}", file=sys.stderr)


# ---------------------------------------------------------------------------
# POST /api/v1/auth/sso/saml/login — Initiate SSO flow
# ---------------------------------------------------------------------------

@router.post("/api/v1/auth/sso/saml/login")
async def sso_saml_login(request: Request):
    """
    Initiate SAML SSO flow. Returns redirect URL to the IdP.

    Body (one of):
      { "invitation_token": "...", "org_id": 123 }    — first-time onboarding
      { "org_domain": "acme.com" }                     — returning user by domain
      { "email": "user@acme.com" }                     — returning user by email
    """
    _require_configured()

    body = await request.json()
    invitation_token = body.get("invitation_token")
    org_id = body.get("org_id")
    org_domain = body.get("org_domain")
    email = body.get("email")

    conn = _get_db_connection()
    try:
        idp_config = None

        if invitation_token and org_id:
            # Onboarding flow: validate invitation, get IdP config for the org
            invitation = validate_invitation_token(conn, invitation_token)
            if not invitation:
                raise HTTPException(status_code=400, detail="Invalid or expired invitation token")
            if invitation["organization_id"] != org_id:
                raise HTTPException(status_code=400, detail="Invitation org_id mismatch")
            idp_config = get_idp_config(conn, org_id)

        elif org_domain:
            idp_config = get_idp_config_by_domain(conn, org_domain)

        elif email and "@" in email:
            domain = email.split("@")[1]
            idp_config = get_idp_config_by_domain(conn, domain)

        if not idp_config:
            raise HTTPException(status_code=404, detail="No SSO configuration found for this organization")

        if not idp_config.get("is_active"):
            raise HTTPException(status_code=400, detail="SSO is disabled for this organization")

        result = generate_authn_request(idp_config, invitation_token=invitation_token)

        _log_sso_event(conn, "sso.login.initiated", {
            "org_id": idp_config["org_id"],
            "invitation_token": invitation_token[-4:] if invitation_token else None,
            "ip": request.client.host if request.client else None,
        })

        return JSONResponse(content={"redirect_url": result["redirect_url"]})

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# POST /api/v1/auth/sso/saml/callback — SAML ACS
# ---------------------------------------------------------------------------

@router.post("/api/v1/auth/sso/saml/callback")
async def sso_saml_callback(
    request: Request,
    SAMLResponse: str = Form(...),
    RelayState: Optional[str] = Form(None),
    org_id: Optional[int] = Query(None),
):
    """
    SAML Assertion Consumer Service. Receives POST from IdP after user auth.

    On success: 302 redirect to dashboard with session cookies set.
    On failure: 401 JSON with structured error code.
    """
    _require_configured()

    conn = _get_db_connection()
    try:
        # Determine which org's IdP config to use
        # org_id may come from query param (added to ACS URL in config)
        # or from the pending request's stored context
        if not org_id:
            raise HTTPException(status_code=400, detail="org_id required in ACS URL query params")

        idp_config = get_idp_config(conn, org_id)
        if not idp_config:
            _log_sso_event(conn, "sso.login.failed", {
                "org_id": org_id,
                "failure_reason": "saml_idp_not_configured",
            })
            raise HTTPException(status_code=401, detail={
                "error": "saml_idp_not_configured",
                "message": "No SSO configuration for this organization",
            })

        # Verify the SAML Response
        try:
            saml_result = verify_saml_response(SAMLResponse, idp_config)
        except SAMLVerificationError as e:
            _log_sso_event(conn, "sso.login.failed", {
                "org_id": org_id,
                "failure_reason": e.code,
                "ip": request.client.host if request.client else None,
            })
            raise HTTPException(status_code=401, detail={
                "error": e.code,
                "message": e.message,
            })

        sso_subject_id = saml_result["sso_subject_id"]
        email = saml_result["email"]
        display_name = saml_result.get("display_name")
        invitation_token = saml_result.get("invitation_token") or RelayState

        # Find or create user
        user = find_user_by_sso(conn, sso_subject_id, org_id)

        if user:
            # Returning user
            if not user["is_active"]:
                raise HTTPException(status_code=401, detail="User account is inactive")

            _log_sso_event(conn, "sso.login.succeeded", {
                "user_id": user["id"],
                "org_id": org_id,
                "sso_subject_id": sso_subject_id,
                "ip": request.client.host if request.client else None,
            })
        else:
            # First-time SSO user — must have a valid invitation
            if not invitation_token:
                raise HTTPException(status_code=403, detail={
                    "error": "sso_no_invitation",
                    "message": "First-time SSO login requires an invitation. Contact your org admin.",
                })

            invitation = validate_invitation_token(conn, invitation_token)
            if not invitation:
                raise HTTPException(status_code=400, detail="Invalid or expired invitation token")

            if invitation["organization_id"] != org_id:
                raise HTTPException(status_code=400, detail="Invitation org mismatch")

            # Use invitation's role if set, otherwise IdP config's default
            role = invitation.get("role") or idp_config.get("default_role", "viewer")

            user = create_sso_user(
                conn=conn,
                email=email,
                name=display_name or email.split("@")[0],
                org_id=org_id,
                role=role,
                sso_subject_id=sso_subject_id,
                sso_provider="saml",
                sso_org_idp_config_id=idp_config["id"],
            )

            mark_invitation_used(conn, invitation_token, user["id"])

            _log_sso_event(conn, "sso.onboarding.succeeded", {
                "user_id": user["id"],
                "org_id": org_id,
                "invitation_token": invitation_token[-4:] if invitation_token else None,
                "role": role,
            })

        # Issue session (same as Web3 flow)
        session = create_session(
            conn=conn,
            user_id=user["id"],
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        # Get org info for display cookies
        org_info = get_org_info(conn, org_id)
        org_name = org_info["org_name"] if org_info else ""

        # Build redirect response with cookies (matches Web3 flow exactly)
        response = RedirectResponse(url=_dashboard_url, status_code=302)

        # Auth cookie (HttpOnly — not readable by JS)
        response.set_cookie(
            key="enterprise_session",
            value=session["session_token"],
            max_age=SESSION_COOKIE_MAX_AGE,
            path="/",
            httponly=True,
            secure=True,
            samesite="lax",
            domain=_cookie_domain,
        )

        # Display cookies (readable by JS for UI)
        response.set_cookie(key="enterprise_email", value=email,
                            max_age=SESSION_COOKIE_MAX_AGE, path="/",
                            secure=True, samesite="lax", domain=_cookie_domain)
        response.set_cookie(key="enterprise_org", value=org_name,
                            max_age=SESSION_COOKIE_MAX_AGE, path="/",
                            secure=True, samesite="lax", domain=_cookie_domain)
        response.set_cookie(key="enterprise_org_id", value=str(org_id),
                            max_age=SESSION_COOKIE_MAX_AGE, path="/",
                            secure=True, samesite="lax", domain=_cookie_domain)
        response.set_cookie(key="enterprise_role", value=user.get("role", "viewer"),
                            max_age=SESSION_COOKIE_MAX_AGE, path="/",
                            secure=True, samesite="lax", domain=_cookie_domain)

        return response

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# GET /api/v1/auth/sso/saml/metadata — SP metadata
# ---------------------------------------------------------------------------

@router.get("/api/v1/auth/sso/saml/metadata")
def sso_saml_metadata(org_id: int = Query(...)):
    """
    Return SP metadata XML for an org, suitable for import into the IdP.
    Public endpoint — IdP admins need to fetch this to configure their side.
    """
    _require_configured()

    conn = _get_db_connection()
    try:
        idp_config = get_idp_config(conn, org_id)
        if not idp_config:
            raise HTTPException(status_code=404, detail="No SSO configuration for this organization")

        metadata_xml = generate_sp_metadata(idp_config)
        return Response(content=metadata_xml, media_type="application/xml")

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Admin endpoints — IdP config management
# ---------------------------------------------------------------------------

@router.post("/api/v1/admin/orgs/{org_id}/idp-config")
async def create_idp_config_endpoint(org_id: int, request: Request):
    """Create or update an org's IdP configuration. Platform admin only."""
    _require_configured()
    admin_user_id, _, _, _ = _require_platform_admin(request)

    body = await request.json()

    required = ["idp_entity_id", "idp_sso_url", "idp_x509_cert"]
    for field in required:
        if not body.get(field):
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    conn = _get_db_connection()
    try:
        # Derive SP defaults if not provided
        org_info = get_org_info(conn, org_id)
        if not org_info:
            raise HTTPException(status_code=404, detail=f"Organization {org_id} not found")

        org_slug = org_info["org_name"].lower().replace(" ", "-")
        sp_entity_id = body.get("sp_entity_id", f"https://app.agenticterminal.io/saml/{org_slug}")
        acs_url = body.get("acs_url", f"https://api.agenticterminal.io/api/v1/auth/sso/saml/callback?org_id={org_id}")

        result = create_or_update_idp_config(
            conn=conn,
            org_id=org_id,
            idp_entity_id=body["idp_entity_id"],
            idp_sso_url=body["idp_sso_url"],
            idp_x509_cert=body["idp_x509_cert"],
            sp_entity_id=sp_entity_id,
            acs_url=acs_url,
            attribute_mapping=body.get("attribute_mapping"),
            default_role=body.get("default_role", "viewer"),
            created_by=admin_user_id,
        )

        _log_sso_event(conn, "sso.config.created", {
            "org_id": org_id,
            "admin_user_id": admin_user_id,
        })

        return JSONResponse(content=result)

    finally:
        conn.close()


@router.get("/api/v1/admin/orgs/{org_id}/idp-config")
def get_idp_config_endpoint(org_id: int, request: Request):
    """Get an org's IdP configuration. Platform admin only."""
    _require_configured()
    _require_platform_admin(request)

    conn = _get_db_connection()
    try:
        config = get_idp_config(conn, org_id)
        if not config:
            raise HTTPException(status_code=404, detail="No SSO configuration for this organization")

        # Redact the certificate in the response (it's large and sensitive)
        safe_config = dict(config)
        cert = safe_config.get("idp_x509_cert", "")
        safe_config["idp_x509_cert"] = f"...{cert[-20:]}" if len(cert) > 20 else cert

        return JSONResponse(content=safe_config)

    finally:
        conn.close()


@router.delete("/api/v1/admin/orgs/{org_id}/idp-config")
def delete_idp_config_endpoint(org_id: int, request: Request):
    """Disable SSO for an org. Platform admin only."""
    _require_configured()
    admin_user_id, _, _, _ = _require_platform_admin(request)

    conn = _get_db_connection()
    try:
        deleted = delete_idp_config(conn, org_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="No active SSO configuration for this organization")

        _log_sso_event(conn, "sso.config.deleted", {
            "org_id": org_id,
            "admin_user_id": admin_user_id,
        })

        return JSONResponse(content={"success": True, "org_id": org_id})

    finally:
        conn.close()
