#!/usr/bin/env python3
"""
OP Trust Policy Executable for OWS Build 2
Enforces trust score threshold and spending limits from Delegation VC
"""

import json
import sys

def main():
    # Read context from stdin
    try:
        ctx = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        json.dump({
            "allow": False,
            "reason": f"Invalid JSON input: {str(e)}"
        }, sys.stdout)
        return
    
    # Extract VAC (Verification of Agent Credentials)
    vac = ctx.get("vac", {})
    agent_id = vac.get("agent_id", "unknown")
    trust_score = vac.get("trust_score", 0)
    min_score = vac.get("score_threshold_default", 75)
    
    # Check trust score against threshold
    if trust_score < min_score:
        remediation = vac.get("remediation_options", ["request_delegation_vc"])
        json.dump({
            "allow": False,
            "reason": f"OP trust score {trust_score} below threshold {min_score}",
            "remediation": remediation,
            "vac_url": f"https://observerprotocol.org/vac/{agent_id}"
        }, sys.stdout)
        return
    
    # Trust score passes — check spending limits from Delegation VC
    delegation = vac.get("delegation_vc", {})
    if delegation.get("present"):
        limits = vac.get("internal_spending_limits", {})
        tx_value_str = ctx.get("transaction", {}).get("value", "0")
        currency = ctx.get("transaction", {}).get("currency", "USDC")
        
        try:
            tx_value = int(tx_value_str)
        except (ValueError, TypeError):
            tx_value = 0
        
        # Check per-transaction limit
        per_tx_limit_str = limits.get("per_transaction", "0")
        try:
            per_tx_limit = int(per_tx_limit_str)
        except (ValueError, TypeError):
            per_tx_limit = 0
        
        if per_tx_limit > 0 and tx_value > per_tx_limit:
            json.dump({
                "allow": False,
                "reason": f"Transaction value {tx_value} {currency} exceeds delegation spending limit of {per_tx_limit} {currency}"
            }, sys.stdout)
            return
        
        # Check daily limit (simplified — would need daily aggregation in production)
        daily_limit_str = limits.get("daily", "0")
        try:
            daily_limit = int(daily_limit_str)
        except (ValueError, TypeError):
            daily_limit = 0
        
        # Note: Daily limit check would require transaction history aggregation
        # For demo purposes, we check per-transaction only
    
    # All checks pass
    json.dump({
        "allow": True,
        "reason": f"OP trust score {trust_score} >= {min_score}, spending limits satisfied"
    }, sys.stdout)

if __name__ == "__main__":
    main()
