"""
AT-side cache invalidation for revoked/suspended credentials.

Implements Spec 3.3 §11: on-demand status re-check when serving cached
credentials from partner_attestations or delegation_credentials.

Invalidation model (from spec):
  - On-demand, not background. Status is re-checked when a cached credential
    is read for a transaction-decision purpose.
  - Re-check if last_verified_at is older than 24 hours AND the credential is
    being used for a transaction decision.
  - For display-only reads (dashboard rendering), serve cached value without
    re-check. UI MAY show last_verified_at.
  - For high-stakes transactions, re-check regardless of cache age.
  - revoked_at is set once and never cleared (revocation is terminal).
  - suspended_at is set when suspension detected, cleared when lifted.
  - Once revoked_at is set, skip re-check on future reads.

Tables affected:
  - partner_attestations (columns: revoked_at, suspended_at, last_verified_at)
  - delegation_credentials (columns: revoked_at, suspended_at, last_verified_at)
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

from status_checker import check_credential_status


# Default re-check threshold
RECHECK_THRESHOLD_HOURS = 24


class CacheStatusResult:
    """Result of checking a cached credential's status."""

    def __init__(
        self,
        credential_id: str,
        is_valid: bool,
        revoked: bool = False,
        suspended: bool = False,
        checked_upstream: bool = False,
        error: Optional[str] = None,
    ):
        self.credential_id = credential_id
        self.is_valid = is_valid
        self.revoked = revoked
        self.suspended = suspended
        self.checked_upstream = checked_upstream
        self.error = error


def check_cached_credential(
    cached_row: dict,
    table_name: str,
    conn,
    fetch_status_list_fn: Callable,
    resolve_did_fn: Optional[Callable] = None,
    force_recheck: bool = False,
) -> CacheStatusResult:
    """
    Check and update the status of a cached credential on read.

    Args:
        cached_row: Dict with the cached credential data. Must contain:
            - credential_id (or id): the credential's identifier
            - credential_jsonld: the full VC JSON (dict or JSON string)
            - last_verified_at: timestamp of last verification (datetime or None)
            - revoked_at: timestamp if revoked (datetime or None)
            - suspended_at: timestamp if suspended (datetime or None)
        table_name: "partner_attestations" or "delegation_credentials"
        conn: Database connection for writing updates.
        fetch_status_list_fn: Callable(url) -> status list credential dict or None.
        resolve_did_fn: Optional callable(did) -> DID document dict for signature
            verification on the status list.
        force_recheck: If True, re-check regardless of last_verified_at age.
            Used for high-stakes transaction decisions.

    Returns:
        CacheStatusResult indicating current validity.
    """
    import json

    credential_id = cached_row.get("credential_id") or cached_row.get("id")
    revoked_at = cached_row.get("revoked_at")
    suspended_at = cached_row.get("suspended_at")
    last_verified_at = cached_row.get("last_verified_at")

    # Already revoked — terminal, no re-check needed
    if revoked_at is not None:
        return CacheStatusResult(
            credential_id=credential_id,
            is_valid=False,
            revoked=True,
            suspended=False,
            checked_upstream=False,
        )

    # Decide whether to re-check upstream
    needs_recheck = force_recheck or _needs_recheck(last_verified_at)

    if not needs_recheck:
        # Return cached state
        is_suspended = suspended_at is not None
        return CacheStatusResult(
            credential_id=credential_id,
            is_valid=not is_suspended,
            revoked=False,
            suspended=is_suspended,
            checked_upstream=False,
        )

    # Re-check upstream
    credential_jsonld = cached_row.get("credential_jsonld")
    if isinstance(credential_jsonld, str):
        credential_jsonld = json.loads(credential_jsonld)

    if not credential_jsonld:
        return CacheStatusResult(
            credential_id=credential_id,
            is_valid=False,
            revoked=False,
            suspended=False,
            checked_upstream=False,
            error="No credential JSON in cache",
        )

    status_result = check_credential_status(
        credential_jsonld,
        fetch_status_list_fn=fetch_status_list_fn,
        resolve_did_fn=resolve_did_fn,
    )

    now = datetime.now(timezone.utc)

    # Determine revocation and suspension from upstream checks
    newly_revoked = False
    newly_suspended = False
    suspension_lifted = False

    for check in status_result.get("status_checks", []):
        if check.get("status_purpose") == "revocation" and not check.get("valid_for_purpose"):
            newly_revoked = True
        if check.get("status_purpose") == "suspension":
            if not check.get("valid_for_purpose"):
                newly_suspended = True
            else:
                # Suspension purpose is clear — if we were previously suspended,
                # this means the suspension was lifted
                if suspended_at is not None:
                    suspension_lifted = True

    # Apply updates to the cache
    _update_cache(
        conn=conn,
        table_name=table_name,
        credential_id=credential_id,
        now=now,
        newly_revoked=newly_revoked,
        newly_suspended=newly_suspended,
        suspension_lifted=suspension_lifted,
    )

    is_valid = not newly_revoked and not newly_suspended
    # If suspension was lifted and no new suspension, credential is valid
    if suspension_lifted and not newly_suspended:
        is_valid = True

    return CacheStatusResult(
        credential_id=credential_id,
        is_valid=is_valid,
        revoked=newly_revoked,
        suspended=newly_suspended,
        checked_upstream=True,
    )


def _needs_recheck(last_verified_at) -> bool:
    """Check if the credential needs upstream re-verification."""
    if last_verified_at is None:
        return True

    if isinstance(last_verified_at, str):
        last_verified_at = datetime.fromisoformat(
            last_verified_at.replace("Z", "+00:00")
        )

    # Handle naive datetimes by assuming UTC
    if last_verified_at.tzinfo is None:
        last_verified_at = last_verified_at.replace(tzinfo=timezone.utc)

    age = datetime.now(timezone.utc) - last_verified_at
    return age > timedelta(hours=RECHECK_THRESHOLD_HOURS)


def _update_cache(
    conn,
    table_name: str,
    credential_id: str,
    now: datetime,
    newly_revoked: bool,
    newly_suspended: bool,
    suspension_lifted: bool,
):
    """
    Write status changes back to the cache table.

    Rules:
      - Always update last_verified_at to now.
      - If newly revoked: set revoked_at = now (terminal, never cleared).
      - If newly suspended: set suspended_at = now.
      - If suspension lifted: clear suspended_at (set to NULL).
    """
    if table_name not in ("partner_attestations", "delegation_credentials"):
        raise ValueError(f"Unknown table: {table_name!r}")

    now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    cursor = conn.cursor()
    try:
        if newly_revoked:
            cursor.execute(
                f"UPDATE {table_name} SET last_verified_at = %s, revoked_at = %s WHERE credential_id = %s",
                (now_str, now_str, credential_id),
            )
        elif newly_suspended:
            cursor.execute(
                f"UPDATE {table_name} SET last_verified_at = %s, suspended_at = %s WHERE credential_id = %s",
                (now_str, now_str, credential_id),
            )
        elif suspension_lifted:
            cursor.execute(
                f"UPDATE {table_name} SET last_verified_at = %s, suspended_at = NULL WHERE credential_id = %s",
                (now_str, credential_id),
            )
        else:
            # No status change, just update last_verified_at
            cursor.execute(
                f"UPDATE {table_name} SET last_verified_at = %s WHERE credential_id = %s",
                (now_str, credential_id),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
