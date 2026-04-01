# OWS Build 2 — OP Trust Policy Executable

**Date:** 2026-04-01  
**Status:** 📋 SPEC — Ready for Leo review, ready for Maxi deployment  
**Repo context:** Companion to [OWS-BUILD-1-LOG.md](./OWS-BUILD-1-LOG.md)

---

## Overview

This document specifies the Observer Protocol Trust Policy Executable — a native OWS policy plugin that gates signing requests on OP VAC trust scores before any key material is touched.

Build 1 (March 24) established OWS agent registration and VAC issuance with OWS badges. Build 2 closes the loop: an agent's OP trust score now enforces access to the OWS signing path itself.

---

## Why This Matters Architecturally

OWS has a native policy executable system. Policies are JSON files that reference an executable at an absolute path. Before every signing operation, OWS pipes the full `PolicyContext` JSON to the executable on stdin and reads a `PolicyResult` JSON from stdout. Non-zero exit or invalid JSON = automatic denial. 5-second timeout enforced.

This means **OP integrates as a first-class OWS primitive** — not middleware, not a wrapper sitting in front of OWS. The OP trust policy is architecturally indistinguishable from any other OWS policy. This is the correct integration model and the strongest possible claim for the hackathon submission.

```
Agent calls ows_sign
        │
        ▼
OWS policy engine
        │
        ├── Declarative rules (fast, in-process)
        │
        └── OP Trust Policy Executable ◄── THIS IS WHAT WE ARE BUILDING
                │
                ▼
        GET /vac/{agent_id}
                │
                ▼
        trust_score >= threshold?
                │
        ┌───────┴───────┐
       YES              NO
        │               │
    allow: true     allow: false
    (sign proceeds) (key never touched)
```

---

## OWS Policy Protocol (from spec)

```
echo '<PolicyContext JSON>' | /path/to/policy-executable
```

**Input — PolicyContext (relevant fields):**

```json
{
  "chain_id": "eip155:8453",
  "wallet_id": "3d98ac26-ff70-42c5-a374-d4c037b3b2fc",
  "api_key_id": "7a2f1b3c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "transaction": {
    "to": "0x742d35Cc...",
    "value": "10000000000000000",
    "raw_hex": "0x02f8...",
    "data": "0x"
  },
  "spending": {
    "daily_total": "50000000000000000",
    "date": "2026-04-03"
  },
  "timestamp": "2026-04-03T10:35:22Z",
  "policy_config": {
    "op_base_url": "https://observerprotocol.org",
    "min_trust_score": 75,
    "agent_key_map": {
      "7a2f1b3c-4d5e-6f7a-8b9c-0d1e2f3a4b5c": "ows-demo-agent"
    }
  }
}
```

Note: `policy_config` is injected automatically by OWS from the policy file's `config` field. This is how we pass OP configuration without hardcoding it in the executable.

**Output — PolicyResult:**

Allow:
```json
{ "allow": true }
```

Deny:
```json
{
  "allow": false,
  "reason": "OP trust score 58 below threshold 75. Remediation options: request_org_attestation, build_transaction_history. VAC: https://observerprotocol.org/vac/ows-demo-agent"
}
```

---

## The Executable

**File:** `/media/nvme/observer-protocol/ows-policy/op-trust-policy.py`

```python
#!/usr/bin/env python3
"""
Observer Protocol Trust Policy for OWS
Native policy executable — integrates OP VAC trust scoring
into the OWS signing path before any key material is touched.

Protocol:
  - Receives PolicyContext JSON on stdin
  - Returns PolicyResult JSON on stdout
  - Must complete within 5 seconds (OWS timeout)
  - Non-zero exit or invalid JSON = automatic denial
"""
import json
import sys
import urllib.request
import urllib.error


def main():
    # Read PolicyContext from stdin
    try:
        ctx = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        result = {"allow": False, "reason": f"Failed to parse PolicyContext: {e}"}
        json.dump(result, sys.stdout)
        sys.exit(0)

    # Extract config injected by OWS from policy file
    config = ctx.get("policy_config", {})
    op_base_url = config.get("op_base_url", "https://observerprotocol.org")
    min_score = config.get("min_trust_score", 75)
    agent_key_map = config.get("agent_key_map", {})

    # Map api_key_id → agent_id
    api_key_id = ctx.get("api_key_id", "")
    agent_id = agent_key_map.get(api_key_id)

    if not agent_id:
        json.dump({
            "allow": False,
            "reason": f"No OP agent_id mapped for api_key_id {api_key_id}. "
                      f"Register this agent at {op_base_url}/observer/register"
        }, sys.stdout)
        sys.exit(0)

    # Call OP VAC endpoint
    vac_url = f"{op_base_url}/vac/{agent_id}"
    try:
        req = urllib.request.Request(
            vac_url,
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            vac = json.load(resp)
    except urllib.error.HTTPError as e:
        json.dump({
            "allow": False,
            "reason": f"OP VAC lookup failed (HTTP {e.code}): {vac_url}"
        }, sys.stdout)
        sys.exit(0)
    except Exception as e:
        json.dump({
            "allow": False,
            "reason": f"OP VAC unreachable: {str(e)}"
        }, sys.stdout)
        sys.exit(0)

    # Extract trust score — support both field names during migration
    score = vac.get("trust_score") or vac.get("reputation_score", 0)

    # Evaluate
    if score >= min_score:
        json.dump({"allow": True}, sys.stdout)
    else:
        org_attested = vac.get("org_attestation", False)
        remediation = []
        if not org_attested:
            remediation.append("request_org_attestation")
        remediation.append("build_transaction_history")

        json.dump({
            "allow": False,
            "reason": (
                f"OP trust score {score} below threshold {min_score}. "
                f"Remediation options: {', '.join(remediation)}. "
                f"VAC: {vac_url}"
            )
        }, sys.stdout)


if __name__ == "__main__":
    main()
```

---

## Policy File

**File:** `~/.ows/policies/op-trust-policy.json`

```json
{
  "id": "op-trust-policy",
  "name": "Observer Protocol Trust Score Gate",
  "version": 1,
  "created_at": "2026-04-01T00:00:00Z",
  "rules": [],
  "executable": "/media/nvme/observer-protocol/ows-policy/op-trust-policy.py",
  "config": {
    "op_base_url": "https://observerprotocol.org",
    "min_trust_score": 75,
    "agent_key_map": {
      "REPLACE_WITH_API_KEY_ID_AFTER_KEY_CREATION": "ows-demo-agent"
    }
  },
  "action": "deny"
}
```

> ⚠️ `agent_key_map` must be updated with the real `api_key_id` after step 4 below.

---

## Deployment Steps (Maxi)

Run these in order. Do not proceed past any step that returns an error.

**Step 1 — Create directory and save executable:**
```bash
mkdir -p /media/nvme/observer-protocol/ows-policy
nano /media/nvme/observer-protocol/ows-policy/op-trust-policy.py
# paste the executable code above
chmod +x /media/nvme/observer-protocol/ows-policy/op-trust-policy.py
```

**Step 2 — Verify executable works in isolation:**
```bash
echo '{"api_key_id": "test", "policy_config": {"op_base_url": "https://observerprotocol.org", "min_trust_score": 75, "agent_key_map": {}}}' | python3 /media/nvme/observer-protocol/ows-policy/op-trust-policy.py
# Expected: {"allow": false, "reason": "No OP agent_id mapped for api_key_id test..."}
```

**Step 3 — Save policy file:**
```bash
mkdir -p ~/.ows/policies
nano ~/.ows/policies/op-trust-policy.json
# paste the policy JSON above
```

**Step 4 — Register demo agent in OP (required before key creation):**
```bash
# Run the updated registration script to create ows-demo-agent in the DB
python3 /media/nvme/observer-protocol/demo/register_ows_demo_agent.py
# Verify:
curl -s https://observerprotocol.org/observer/agent/ows-demo-agent | python3 -m json.tool
```

**Step 5 — Create OWS API key with policy attached:**
```bash
ows policy create --file ~/.ows/policies/op-trust-policy.json
ows key create --name "op-demo-agent" --wallet agent-treasury --policy op-trust-policy
# ⚠️ IMPORTANT: Copy the returned api_key_id and ows_key_... token
# Store the token securely — shown only once
```

**Step 6 — Update agent_key_map with real api_key_id:**
```bash
nano ~/.ows/policies/op-trust-policy.json
# Replace "REPLACE_WITH_API_KEY_ID_AFTER_KEY_CREATION" with the actual api_key_id
# Re-register the policy:
ows policy create --file ~/.ows/policies/op-trust-policy.json
```

**Step 7 — End-to-end denial test:**
```bash
# This should DENY because ows-demo-agent has no org attestation yet (score < 75)
ows sign message \
  --wallet agent-treasury \
  --chain eip155:8453 \
  --message "test" \
  --key ows_key_YOUR_TOKEN_HERE
# Expected: POLICY_DENIED — OP trust score X below threshold 75
```

---

## Open Question for Leo

> **Q: Does the `api_key_id → agent_id` mapping approach work with the current W3C DID architecture?**

The policy executable maps the OWS `api_key_id` to an OP `agent_id` via a static lookup table in the policy config. This is the simplest approach and avoids any runtime coupling between OWS key management and OP identity.

The alternative would be embedding the OP `agent_id` or `did` directly in the OWS API key metadata at creation time — but OWS doesn't currently support arbitrary metadata on API keys, so the config map is the right approach for now.

Leo: please confirm this is sound given the DID architecture, or flag if there's a cleaner binding mechanism we should use.

---

## Test Verification Checklist

Before the demo, confirm all of these:

- [ ] `op-trust-policy.py` is executable and returns valid JSON in isolation (Step 2)
- [ ] `ows-demo-agent` exists in OP DB and VAC endpoint returns JSON
- [ ] VAC response includes `trust_score` field (or `reputation_score` as fallback)
- [ ] OWS API key created with policy attached
- [ ] `agent_key_map` updated with real `api_key_id`
- [ ] Step 7 denial test returns `POLICY_DENIED` with OP reason string
- [ ] After org attestation approved: trust_score >= 75, Step 7 returns success

---

## What This Enables in the Demo

| Demo Beat | What Happens | What the Audience Sees |
|---|---|---|
| Beat 1 — DENY | Agent calls `ows sign`, policy executable fires, VAC score 58 < 75 | `POLICY_DENIED: OP trust score 58 below threshold 75` |
| Beat 4 — RESOLVE | Org attestation approved, score recomputes to 82, agent retries | `ows sign` succeeds, `ows pay request` executes real x402 transaction |

---

*Spec prepared by Boyd Cohen + Claude, 2026-04-01*  
*Questions: raise as GitHub issues or in the team channel*
