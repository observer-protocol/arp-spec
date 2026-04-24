"""
Policy consultation client — OP calls the registered engine before commits.

Flow:
  1. Look up org's registered engine
  2. If none → permit-by-default
  3. Build evaluation request with action context
  4. Sign request with OP's key
  5. POST to engine URL with timeout
  6. Verify engine's signature on response
  7. Return decision (permit/deny/pending_approval)
  8. Log always, regardless of outcome

Fail-closed: if engine is unreachable or signature invalid, return UNAVAILABLE.
Rate limit: in-memory per-org, 100 calls/sec.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable

import httpx

from policy_engine_store import get_engine, log_consultation


class PolicyDecision(str, Enum):
    PERMIT = "permit"
    DENY = "deny"
    PENDING_APPROVAL = "pending_approval"
    UNAVAILABLE = "unavailable"
    SIGNATURE_INVALID = "signature_invalid"


class PolicyResult:
    def __init__(
        self,
        decision: PolicyDecision,
        request_id: str,
        policy_id: Optional[str] = None,
        reason: Optional[str] = None,
        violations: Optional[list] = None,
        approval_status_url: Optional[str] = None,
        engine_signature: Optional[str] = None,
        raw_response: Optional[dict] = None,
    ):
        self.decision = decision
        self.request_id = request_id
        self.policy_id = policy_id
        self.reason = reason
        self.violations = violations
        self.approval_status_url = approval_status_url
        self.engine_signature = engine_signature
        self.raw_response = raw_response


# In-memory rate limiter: org_id -> (count, window_start)
_rate_limits: dict[int, tuple[int, float]] = {}
RATE_LIMIT_PER_SEC = 100
ENGINE_TIMEOUT_SECONDS = 5


def _check_rate_limit(org_id: int) -> bool:
    """Returns True if within limit, False if exceeded."""
    now = time.time()
    entry = _rate_limits.get(org_id)
    if entry is None or now - entry[1] >= 1.0:
        _rate_limits[org_id] = (1, now)
        return True
    count, window_start = entry
    if count >= RATE_LIMIT_PER_SEC:
        return False
    _rate_limits[org_id] = (count + 1, window_start)
    return True


def consult_policy_engine(
    conn,
    org_id: int,
    action_type: str,
    action_context: dict,
    sign_request_fn: Optional[Callable] = None,
    verify_signature_fn: Optional[Callable] = None,
) -> PolicyResult:
    """
    Consult the registered policy engine for an org.

    Args:
        conn: DB connection (for engine lookup and logging).
        org_id: The org whose engine to consult.
        action_type: e.g. 'transaction.submit', 'delegation.grant', 'credential.revoke'
        action_context: Full context dict for the engine to evaluate.
        sign_request_fn: Optional callable(body_bytes) -> signature_str.
            Signs the outbound request with OP's key.
        verify_signature_fn: Optional callable(body_bytes, signature_str, public_key_did) -> bool.
            Verifies the engine's signature on the response.

    Returns:
        PolicyResult with decision and metadata.
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()

    # 1. Look up engine
    engine = get_engine(conn, org_id)
    if engine is None:
        # No engine registered → permit-by-default
        result = PolicyResult(
            decision=PolicyDecision.PERMIT,
            request_id=request_id,
            reason="no_engine_registered",
        )
        log_consultation(
            conn, org_id, "none", request_id, action_type,
            "permit", {"reason": "no_engine_registered"},
        )
        return result

    engine_url = engine["engine_url"]
    engine_key_did = engine["engine_public_key_did"]

    # 2. Rate limit
    if not _check_rate_limit(org_id):
        result = PolicyResult(
            decision=PolicyDecision.UNAVAILABLE,
            request_id=request_id,
            reason="rate_limit_exceeded",
        )
        log_consultation(
            conn, org_id, engine_url, request_id, action_type,
            "unavailable", {"reason": "rate_limit_exceeded"},
        )
        return result

    # 3. Build request
    eval_request = {
        "request_id": request_id,
        "org_id": org_id,
        "action_type": action_type,
        "action_context": action_context,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    headers = {
        "Content-Type": "application/json",
        "X-OP-Request-Id": request_id,
    }

    # Sign the request if signing function available
    request_body = json.dumps(eval_request, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if sign_request_fn:
        try:
            headers["X-OP-Signature"] = sign_request_fn(request_body)
        except Exception:
            pass  # Non-fatal: engine may not require OP signature

    # 4. Call engine
    try:
        with httpx.Client(timeout=ENGINE_TIMEOUT_SECONDS) as client:
            response = client.post(engine_url, json=eval_request, headers=headers)

        if response.status_code != 200:
            elapsed_ms = int((time.time() - start_time) * 1000)
            result = PolicyResult(
                decision=PolicyDecision.UNAVAILABLE,
                request_id=request_id,
                reason=f"engine_returned_{response.status_code}",
            )
            log_consultation(
                conn, org_id, engine_url, request_id, action_type,
                "unavailable",
                {"reason": f"engine_returned_{response.status_code}", "body": response.text[:500]},
                eval_duration_ms=elapsed_ms,
            )
            return result

        response_data = response.json()

    except httpx.TimeoutException:
        elapsed_ms = int((time.time() - start_time) * 1000)
        result = PolicyResult(
            decision=PolicyDecision.UNAVAILABLE,
            request_id=request_id,
            reason="engine_timeout",
        )
        log_consultation(
            conn, org_id, engine_url, request_id, action_type,
            "unavailable", {"reason": "engine_timeout"},
            eval_duration_ms=elapsed_ms,
        )
        return result
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        result = PolicyResult(
            decision=PolicyDecision.UNAVAILABLE,
            request_id=request_id,
            reason=f"engine_error: {str(e)[:200]}",
        )
        log_consultation(
            conn, org_id, engine_url, request_id, action_type,
            "unavailable", {"reason": str(e)[:500]},
            eval_duration_ms=elapsed_ms,
        )
        return result

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 5. Verify engine signature
    engine_signature = response_data.get("signature")
    if verify_signature_fn and engine_signature:
        response_for_verify = {k: v for k, v in response_data.items() if k != "signature"}
        verify_bytes = json.dumps(response_for_verify, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            sig_valid = verify_signature_fn(verify_bytes, engine_signature, engine_key_did)
        except Exception:
            sig_valid = False

        if not sig_valid:
            result = PolicyResult(
                decision=PolicyDecision.SIGNATURE_INVALID,
                request_id=request_id,
                reason="engine_signature_verification_failed",
                raw_response=response_data,
            )
            log_consultation(
                conn, org_id, engine_url, request_id, action_type,
                "signature_invalid",
                {"reason": "signature_verification_failed", "response": response_data},
                engine_signature=engine_signature,
                eval_duration_ms=elapsed_ms,
            )
            return result

    # 6. Parse decision
    decision_str = response_data.get("decision", "").lower()
    if decision_str == "permit":
        decision = PolicyDecision.PERMIT
    elif decision_str == "deny":
        decision = PolicyDecision.DENY
    elif decision_str == "pending_approval":
        decision = PolicyDecision.PENDING_APPROVAL
    else:
        decision = PolicyDecision.UNAVAILABLE
        response_data["reason"] = f"unknown_decision: {decision_str}"

    result = PolicyResult(
        decision=decision,
        request_id=request_id,
        policy_id=response_data.get("policy_id"),
        reason=response_data.get("reason"),
        violations=response_data.get("violations"),
        approval_status_url=response_data.get("approval_status_url"),
        engine_signature=engine_signature,
        raw_response=response_data,
    )

    log_consultation(
        conn, org_id, engine_url, request_id, action_type,
        decision.value, response_data,
        policy_id=response_data.get("policy_id"),
        engine_signature=engine_signature,
        eval_duration_ms=elapsed_ms,
    )

    return result
