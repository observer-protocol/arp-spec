#!/usr/bin/env python3
"""
Institutional Bilateral Demo — Observer Protocol / Agentic Terminal

Demonstrates the 8-beat institutional flow:
1. Discovery & handshake (DID exchange, tier mismatch visible)
2. Eager chain verification (Tier 2 insufficient)
3. Policy-layer rejection (structured AIP refusal)
4. Autonomous remediation request
5. Human approval (CIO selects Tier 3 in dashboard)
6. One-click ERC-8004 publication
7. Retry and settlement on x402/USDC
8. Audit trail in both dashboards

Usage:
    python setup_agents.py   # Run once to register agents
    python demo.py           # Run the 8-beat demo
    python demo.py --beat 3  # Run a specific beat

Requirements:
    pip install httpx cryptography observer-protocol
"""

import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

OP_API = "https://api.observerprotocol.org"
DEMO_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(DEMO_DIR, "demo_config.json")
AUDIT_LOG = os.path.join(DEMO_DIR, "audit_log.jsonl")

# ── Load config ──────────────────────────────────────────────

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("Error: Run setup_agents.py first")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)


def sign_payload(private_key_hex, payload):
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return key.sign(canonical.encode()).hex()


def log_audit(entry):
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def pause(msg=""):
    if msg:
        print(f"\n  {msg}")
    input("  [Press Enter to continue]\n")


# ── Beat 1: Discovery & Handshake ────────────────────────────

def beat_1(config):
    print()
    print("=" * 70)
    print("BEAT 1  |  Discovery and Handshake")
    print("=" * 70)
    print()

    fa = config["fund_a"]
    lb = config["lender_b"]

    print(f"  Fund A agent: {fa['agent_name']}")
    print(f"    DID:  {fa['agent_did']}")
    print(f"    Tier: Tier 2 (Enterprise-Attested)")
    print(f"    AT-ARS: {fa['at_ars_score']}")
    print()
    print(f"  Lender B agent: {lb['agent_name']}")
    print(f"    DID:  {lb['agent_did']}")
    print(f"    Tier: Tier 3 (Enterprise + Chain-Anchored)")
    print(f"    AT-ARS: {lb['at_ars_score']}")
    print()

    # Resolve DIDs
    print("  [DID Resolution]")
    for name, agent in [("Fund A", fa), ("Lender B", lb)]:
        try:
            resp = httpx.get(f"{OP_API}/agents/{agent['agent_id']}/did.json", timeout=10)
            if resp.status_code == 200:
                print(f"    {name}: DID resolved successfully")
            else:
                print(f"    {name}: DID resolution returned {resp.status_code}")
        except Exception as e:
            print(f"    {name}: DID resolution failed ({e})")

    print()
    print("  >> Tier mismatch visible: Fund A = Tier 2, Lender B = Tier 3")

    log_audit({
        "beat": 1, "event": "discovery_handshake",
        "fund_a_did": fa["agent_did"], "fund_a_tier": "enterprise",
        "lender_b_did": lb["agent_did"], "lender_b_tier": "chain-anchored",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Beat 2: Eager Chain Verification ─────────────────────────

def beat_2(config):
    print()
    print("=" * 70)
    print("BEAT 2  |  Eager Chain Verification - Tier Mismatch Surfaced")
    print("=" * 70)
    print()

    fa = config["fund_a"]
    tx = config["transaction"]
    policy = config["lender_b_policy"]

    print(f"  Transaction: ${int(tx['amount']):,} {tx['currency']} margin top-up")
    print(f"  Rail: {tx['rail']}")
    print()
    print("  [Lender B verifies Fund A against ERC-8004 registry]")
    print()
    print(f"    Fund A attestation tier: Tier 2 (Enterprise-Attested)")
    print(f"    Required for >= ${int(policy['tier_threshold_amount']):,}: Tier 3 (Chain-Anchored)")
    print(f"    ERC-8004 on-chain anchor: NOT FOUND")
    print()
    print("  >> MISMATCH: Tier 2 received, Tier 3 required for this transaction size")

    log_audit({
        "beat": 2, "event": "chain_verification",
        "agent_did": fa["agent_did"],
        "tier_found": "enterprise", "tier_required": "chain-anchored",
        "transaction_amount": tx["amount"],
        "threshold": policy["tier_threshold_amount"],
        "result": "MISMATCH",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Beat 3: Policy-Layer Rejection ───────────────────────────

def beat_3(config):
    print()
    print("=" * 70)
    print("BEAT 3  |  Policy-Layer Rejection")
    print("=" * 70)
    print()

    fa = config["fund_a"]
    policy = config["lender_b_policy"]

    refusal = {
        "verdict": "rejected",
        "aip_version": "0.5.1",
        "violations": [
            {
                "code": "ATTESTATION_TIER_INSUFFICIENT",
                "message": f"Tier 2 (Enterprise-Attested) received; Tier 3 (Chain-Anchored) required for transactions >= ${int(policy['tier_threshold_amount']):,}",
                "required_tier": "chain-anchored",
                "received_tier": "enterprise",
            },
            {
                "code": "AT_ARS_BELOW_THRESHOLD",
                "message": f"AT-ARS score {fa['at_ars_score']} below counterparty minimum of {policy['min_at_ars']}",
                "required_score": policy["min_at_ars"],
                "received_score": fa["at_ars_score"],
            },
        ],
        "remediation": {
            "type": "upgrade_attestation_tier",
            "target_tier": "chain-anchored",
            "target_score": policy["min_at_ars"],
            "hint": "Request a Tier 3 Delegation Credential with ERC-8004 chain anchoring. Chain-anchored attestation will also contribute +9 to AT-ARS score.",
        },
    }

    print("  [AIP v0.5.1 Structured Refusal]")
    print()
    print(f"  Verdict: REJECTED")
    print()
    print(f"  Violation 1: {refusal['violations'][0]['code']}")
    print(f"    {refusal['violations'][0]['message']}")
    print()
    print(f"  Violation 2: {refusal['violations'][1]['code']}")
    print(f"    {refusal['violations'][1]['message']}")
    print()
    print(f"  Remediation hint:")
    print(f"    {refusal['remediation']['hint']}")
    print()
    print("  >> Smart contract is Immunefi-audited and would execute.")
    print("  >> Rejection happens at the agent principal layer - the gap OP/AT fills.")

    log_audit({
        "beat": 3, "event": "policy_rejection",
        "refusal": refusal,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return refusal


# ── Beat 4: Autonomous Remediation ───────────────────────────

def beat_4(config, refusal):
    print()
    print("=" * 70)
    print("BEAT 4  |  Autonomous Remediation Request")
    print("=" * 70)
    print()

    fa = config["fund_a"]
    tx = config["transaction"]

    print("  [Fund A's agent parses the AIP refusal payload]")
    print()
    print(f"    Missing: {refusal['remediation']['target_tier']} attestation")
    print(f"    Score gap: {fa['at_ars_score']} -> need {refusal['remediation']['target_score']}")
    print(f"    Remediation path: {refusal['remediation']['type']}")
    print()

    # Auto-submit delegation request
    delegation_request = {
        "agent_id": fa["agent_id"],
        "requested_tier": "chain-anchored",
        "scope": ["margin-topup", "collateral-release"],
        "rails": ["x402-usdc-base", "lightning", "tron:trc20"],
        "spending_limits": {
            "per_transaction": tx["amount"],
            "daily": str(int(tx["amount"]) * 3),
            "currency": tx["currency"],
        },
        "expiration": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "reason": "Autonomous remediation: counterparty requires Tier 3 for transaction >= $1M",
    }

    print("  [Agent auto-submits Delegation Credential request]")
    print(f"    Tier: Tier 3 (Enterprise + Chain-Anchored)")
    print(f"    Scope: margin-topup, collateral-release")
    print(f"    Rails: x402-usdc-base, lightning, tron:trc20")
    print(f"    Per-tx limit: ${int(tx['amount']):,} {tx['currency']}")
    print(f"    Expiry: 30 days")
    print()
    print("  >> Request appears in Fund A's CIO console.")
    print("  >> No human was in the loop until now.")

    # Submit to OP
    try:
        resp = httpx.post(f"{OP_API}/observer/request-delegation", json={
            "agent_id": fa["agent_id"],
            "org_did": "did:web:fund-a.institutional.demo",
            "requested_by": "agent-autonomous-remediation",
            "scope": delegation_request["scope"],
            "rails": delegation_request["rails"],
            "spending_limits": delegation_request["spending_limits"],
            "expiration": delegation_request["expiration"],
            "attestation_tier": "chain-anchored",
        }, timeout=10)
        if resp.status_code in (200, 201):
            data = resp.json()
            print(f"\n  >> Delegation request submitted: {data.get('request_id', 'OK')}")
            delegation_request["request_id"] = data.get("request_id")
        else:
            print(f"\n  >> API returned {resp.status_code} (demo continues)")
    except Exception as e:
        print(f"\n  >> API call failed ({e}) - demo continues with simulated flow")

    log_audit({
        "beat": 4, "event": "autonomous_remediation",
        "delegation_request": delegation_request,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return delegation_request


# ── Beat 5: Human Approval ───────────────────────────────────

def beat_5(config, delegation_request):
    print()
    print("=" * 70)
    print("BEAT 5  |  Human Approval - CIO Selects Tier 3")
    print("=" * 70)
    print()

    print("  [AT Enterprise Dashboard - Fund A CIO Console]")
    print()
    print("  Issue Delegation Wizard - Step 2 of 5: Attestation Tier")
    print()
    print("    [ ] Tier 1: Self-Attested (Sovereign only)")
    print("        Principal signs with self-custodied key")
    print()
    print("    [ ] Tier 2: Enterprise-Attested")
    print("        Issued by enterprise admin with organizational authority")
    print()
    print("    [*] Tier 3: Enterprise + Chain-Anchored  <-- SELECTED")
    print("        Enterprise attestation with cryptographic publication")
    print("        on ERC-8004 registry")
    print()
    print(f"  Scope: {', '.join(delegation_request.get('scope', ['margin-topup']))}")
    print(f"  Rails: x402-usdc-base, lightning, tron:trc20")
    print(f"  Expiry: 30 days")
    print()
    print("  >> CIO approves with hardware key signature.")
    print("  >> Open the AT dashboard to execute this step live:")
    print(f"     https://app.agenticterminal.io/delegations")

    log_audit({
        "beat": 5, "event": "human_approval",
        "tier_selected": "chain-anchored",
        "approved_by": "CIO (hardware key)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Beat 6: ERC-8004 Publication ─────────────────────────────

def beat_6(config):
    print()
    print("=" * 70)
    print("BEAT 6  |  One-Click ERC-8004 Publication")
    print("=" * 70)
    print()

    fa = config["fund_a"]

    # Pin registration file
    print("  [Pinning registration file...]")
    try:
        resp = httpx.post(f"{OP_API}/api/v1/erc8004/registration/pin", json={
            "agent_id": fa["agent_id"],
            "agent_did": fa["agent_did"],
            "agent_name": fa["agent_name"],
            "description": "Institutional treasury agent - Fund A",
        }, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            serving_url = data.get("serving_url", f"{OP_API}/agents/{fa['agent_id']}/registration.json")
            content_hash = data.get("content_hash", hashlib.sha256(json.dumps(data).encode()).hexdigest())
        else:
            serving_url = f"{OP_API}/agents/{fa['agent_id']}/registration.json"
            content_hash = "simulated_hash"
    except Exception:
        serving_url = f"{OP_API}/agents/{fa['agent_id']}/registration.json"
        content_hash = "simulated_hash"

    print(f"    Registration file pinned")
    print(f"    Token URI: {serving_url}")
    print(f"    Content hash (SHA-256): {content_hash[:32]}...")
    print()
    print("  [Mint 8004 NFT on Base]")
    print(f"    Contract: 0x8004A169FB4a3325136EB29fA0ceB6D2e539a432")
    print(f"    Function: register(tokenURI)")
    print(f"    Chain: Base mainnet (eip155:8453)")
    print()

    # Simulated AT-ARS recompute
    old_score = config["fund_a"]["at_ars_score"]
    new_score = old_score + 13  # +9 chain anchor, +4 hardware key
    config["fund_a"]["at_ars_score"] = new_score

    print(f"  [AT-ARS Recompute]")
    print(f"    Chain-anchored attestation: +9")
    print(f"    Hardware-key CIO approval:  +4")
    print(f"    New AT-ARS score: {old_score} -> {new_score}")
    print()
    print("  >> Fund A is now Tier 3 with AT-ARS {new_score}.")
    print("  >> Credential authorizes x402, Lightning, and TRON settlement.")
    print()
    print("  >> Execute this step live in the AT dashboard:")
    print(f"     https://app.agenticterminal.io/delegations")

    log_audit({
        "beat": 6, "event": "erc8004_publication",
        "token_uri": serving_url,
        "content_hash": content_hash,
        "contract": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
        "old_score": old_score, "new_score": new_score,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Beat 7: Retry and Settlement ─────────────────────────────

def beat_7(config):
    print()
    print("=" * 70)
    print("BEAT 7  |  Retry and Settlement on x402 / USDC")
    print("=" * 70)
    print()

    fa = config["fund_a"]
    lb = config["lender_b"]
    tx = config["transaction"]
    policy = config["lender_b_policy"]

    print("  [Fund A re-presents updated VAC]")
    print()
    print("  [Lender B independent verification against ERC-8004]")
    print(f"    Chain-anchored Tier 3 attestation: PASS")
    print(f"    AT-ARS score {fa['at_ars_score']} >= {policy['min_at_ars']}: PASS")
    print(f"    Transaction within authorized scope: PASS")
    print(f"    x402-usdc-base in credential Rails field: PASS")
    print()
    print("  >> ALL CHECKS PASS")
    print()

    # Settlement
    agent_id = fa["agent_id"]
    now_str = datetime.now().isoformat()
    settlement_tx = "0x" + hashlib.sha256(f"{agent_id}{now_str}".encode()).hexdigest()[:64]

    print(f"  [Settlement executing on x402 / USDC on Base]")
    print(f"    Amount: ${int(tx['amount']):,} {tx['currency']}")
    print(f"    Rail: {tx['rail']}")
    print(f"    TX hash: {settlement_tx[:18]}...{settlement_tx[-8:]}")
    print()

    # Receipt
    receipt_id = f"urn:uuid:{uuid.uuid4()}"
    print(f"  [Signed receipt issued]")
    print(f"    Receipt: {receipt_id}")
    print(f"    References:")
    print(f"      - Delegation Credential Token URI")
    print(f"      - ERC-8004 anchor transaction hash")
    print(f"      - CIO hardware-key approval event")
    print()
    print("  >> Same credential would settle on Lightning or TRON")
    print("  >> if the counterparty preferred.")

    log_audit({
        "beat": 7, "event": "settlement",
        "amount": tx["amount"], "currency": tx["currency"], "rail": tx["rail"],
        "settlement_tx": settlement_tx,
        "receipt_id": receipt_id,
        "verification": {
            "tier": "PASS", "score": "PASS", "scope": "PASS", "rail": "PASS",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Beat 8: Audit Trail ─────────────────────────────────────

def beat_8(config):
    print()
    print("=" * 70)
    print("BEAT 8  |  Audit Trail in Both Dashboards")
    print("=" * 70)
    print()

    fa = config["fund_a"]
    lb = config["lender_b"]

    print("  FUND A's VIEW                     LENDER B's VIEW")
    print("  " + "-" * 30 + "   " + "-" * 30)
    print("  1. Refusal received               1. Refusal issued (policy)")
    print("  2. Auto-remediation sent          2. Remediation hint sent")
    print("  3. Tier 3 credential issued       3. Token URI resolved (8004)")
    print("  4. ERC-8004 publication tx        4. Content hash verified")
    print("  5. CIO hardware-key approval      5. Settlement approved")
    print("  6. Settlement on x402/USDC        6. Signed receipt issued")
    print()
    print("  Both views are independently verifiable against the on-chain registry.")
    print()
    print("  >> Every party has the full trail: Fund A, Lender B, Anchorage,")
    print("     a regulator, or an auditor with no relationship to either party.")
    print()
    print("  >> View live dashboards:")
    print(f"     Fund A:   https://app.agenticterminal.io/enterprise/dashboard")
    print(f"     Lender B: https://app.agenticterminal.io/enterprise/dashboard")
    print()
    print("  Audit log saved to: " + AUDIT_LOG)

    log_audit({
        "beat": 8, "event": "audit_trail_complete",
        "fund_a_did": fa["agent_did"],
        "lender_b_did": lb["agent_did"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Main ─────────────────────────────────────────────────────

def main():
    config = load_config()

    specific_beat = None
    if len(sys.argv) > 2 and sys.argv[1] == "--beat":
        specific_beat = int(sys.argv[2])

    print()
    print("*" * 70)
    print("  INSTITUTIONAL BILATERAL DEMO")
    print("  Observer Protocol / Agentic Terminal")
    print("  Tiered attestations | ERC-8004 | Multi-rail settlement")
    print("*" * 70)
    print()
    print(f"  Transaction: ${int(config['transaction']['amount']):,} USDC margin top-up")
    print(f"  Rail: x402 / USDC on Base")
    print(f"  Fund A: Tier 2, AT-ARS {config['fund_a']['at_ars_score']}")
    print(f"  Lender B: Tier 3, AT-ARS {config['lender_b']['at_ars_score']}")
    print(f"  Policy: Tier 3 required for >= ${int(config['lender_b_policy']['tier_threshold_amount']):,}")

    if specific_beat:
        beats = {1: beat_1, 2: beat_2, 3: beat_3, 5: beat_5, 6: beat_6, 7: beat_7, 8: beat_8}
        if specific_beat == 4:
            refusal = beat_3(config)
            beat_4(config, refusal)
        elif specific_beat in beats:
            beats[specific_beat](config)
        return

    # Full demo
    beat_1(config)
    pause("Beat 1 complete. Next: Eager chain verification.")

    beat_2(config)
    pause("Beat 2 complete. Next: Policy-layer rejection.")

    refusal = beat_3(config)
    pause("Beat 3 complete. Next: Autonomous remediation.")

    delegation_request = beat_4(config, refusal)
    pause("Beat 4 complete. Next: Human approval in AT dashboard.")

    beat_5(config, delegation_request)
    pause("Beat 5 complete. Next: ERC-8004 publication.")

    beat_6(config)
    pause("Beat 6 complete. Next: Retry and settlement.")

    beat_7(config)
    pause("Beat 7 complete. Next: Audit trail.")

    beat_8(config)

    print()
    print("*" * 70)
    print("  DEMO COMPLETE")
    print("  Full audit trail in: " + AUDIT_LOG)
    print("*" * 70)


if __name__ == "__main__":
    main()
