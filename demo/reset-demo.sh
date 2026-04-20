#!/bin/bash
psql
postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db -c "UPDATE observer_agents SET delegation_vc = NULL, delegation_vc_present = FALSE, trust_score = 58, org_did = NULL WHERE alias = 'ows-demo-agent';"
echo "Reset complete" 
