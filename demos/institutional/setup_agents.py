#!/usr/bin/env python3
"""
Setup script for the Institutional Bilateral Demo.

Registers Fund A and Lender B agents on Observer Protocol,
verifies them, and outputs the agent IDs + DIDs for the demo harness.

Run once before the demo:
    python setup_agents.py
"""

import json
import sys
sys.path.insert(0, '../../sdk/python')

from observer_protocol import ObserverClient

client = ObserverClient()

print("=" * 60)
print("Institutional Demo — Agent Setup")
print("=" * 60)
print()

# ── Fund A Treasury Agent ────────────────────────────────────

print("[1] Registering Fund A Treasury Agent...")
pub_a, priv_a = ObserverClient.generate_keypair()
agent_a = client.register_agent(
    public_key=pub_a,
    agent_name="Fund A Treasury Agent",
    alias="agent-fund-a-treasury-01",
)
print(f"    Agent ID: {agent_a.agent_id}")
print(f"    DID: {agent_a.agent_did}")

# Verify
challenge_a = client.request_challenge(agent_a.agent_id)
sig_a = ObserverClient.sign_challenge(priv_a, challenge_a.nonce)
client.verify_agent(agent_a.agent_id, sig_a)
print(f"    Verified: YES")
print()

# ── Lender B Protocol Agent ──────────────────────────────────

print("[2] Registering Lender B Protocol Agent...")
pub_b, priv_b = ObserverClient.generate_keypair()
agent_b = client.register_agent(
    public_key=pub_b,
    agent_name="Lender B Protocol Agent",
    alias="agent-lender-b-protocol-01",
)
print(f"    Agent ID: {agent_b.agent_id}")
print(f"    DID: {agent_b.agent_did}")

# Verify
challenge_b = client.request_challenge(agent_b.agent_id)
sig_b = ObserverClient.sign_challenge(priv_b, challenge_b.nonce)
client.verify_agent(agent_b.agent_id, sig_b)
print(f"    Verified: YES")
print()

# ── Save config ──────────────────────────────────────────────

config = {
    "fund_a": {
        "agent_id": agent_a.agent_id,
        "agent_did": agent_a.agent_did,
        "agent_name": "Fund A Treasury Agent",
        "public_key": pub_a,
        "private_key": priv_a,
        "tier": "enterprise",
        "at_ars_score": 71,
    },
    "lender_b": {
        "agent_id": agent_b.agent_id,
        "agent_did": agent_b.agent_did,
        "agent_name": "Lender B Protocol Agent",
        "public_key": pub_b,
        "private_key": priv_b,
        "tier": "chain-anchored",
        "at_ars_score": 88,
    },
    "transaction": {
        "amount": "1200000",
        "currency": "USDC",
        "rail": "x402-usdc-base",
        "description": "Margin top-up to maintain LTV after price move",
        "threshold": "1000000",
    },
    "lender_b_policy": {
        "min_at_ars": 80,
        "min_tier": "chain-anchored",
        "tier_threshold_amount": "1000000",
    },
}

with open("demo_config.json", "w") as f:
    json.dump(config, f, indent=2)

print("[3] Config saved to demo_config.json")
print()
print("Next: python demo.py")
print("=" * 60)
