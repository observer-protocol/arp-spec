# Institutional Bilateral Demo

Tiered attestations, one-click ERC-8004 publication, multi-rail settlement.

## Scenario

Fund A (hedge fund treasury agent) attempts a $1.2M USDC margin top-up to Lender B (DeFi lending protocol). Lender B requires Tier 3 chain-anchored attestation for transactions >= $1M. Fund A has Tier 2. The demo shows the rejection, autonomous remediation, CIO upgrade to Tier 3, ERC-8004 publication, and settlement.

## Run

```bash
pip install httpx cryptography observer-protocol

# Step 1: Register demo agents
python setup_agents.py

# Step 2: Run the 8-beat demo
python demo.py

# Or run a specific beat
python demo.py --beat 3
```

## The Eight Beats

1. **Discovery & Handshake** - DID exchange, tier mismatch visible
2. **Eager Chain Verification** - Tier 2 insufficient for $1.2M
3. **Policy-Layer Rejection** - AIP structured refusal with remediation hint
4. **Autonomous Remediation** - Agent auto-requests Tier 3 upgrade
5. **Human Approval** - CIO selects Tier 3 in AT dashboard wizard
6. **ERC-8004 Publication** - One-click pin + mint on Base
7. **Retry & Settlement** - x402/USDC on Base, all checks pass
8. **Audit Trail** - Both dashboards, independently verifiable

## Live surfaces (use alongside the demo)

- AT Enterprise Dashboard: https://app.agenticterminal.io/enterprise/dashboard
- Delegations (Issue Credential): https://app.agenticterminal.io/delegations
- Sovereign Dashboard: https://app.agenticterminal.io/sovereign/dashboard

## Files

- `setup_agents.py` - register Fund A + Lender B agents
- `demo.py` - 8-beat orchestrated demo
- `demo_config.json` - generated agent config
- `audit_log.jsonl` - generated audit trail
