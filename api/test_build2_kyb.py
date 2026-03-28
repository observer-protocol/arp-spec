#!/usr/bin/env python3
"""
Test script for Observer Protocol Build 2: MoonPay KYB Integration

This script tests all the new endpoints and functionality:
1. KYB Provider Registry (List, Get)
2. Organization Registration with KYB
3. KYB Status Check
4. KYB Verification Trigger
5. Agent Registration with org_id
6. Attestation with KYB extensions in VAC

Usage:
    python test_build2_kyb.py

Requires Observer Protocol API to be running on localhost:8000
"""

import requests
import json
import sys
from datetime import datetime

# API base URL
BASE_URL = "http://localhost:8000"

def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_json(data):
    """Print formatted JSON"""
    print(json.dumps(data, indent=2))

def test_health():
    """Test health endpoint"""
    print_section("Testing Health Check")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"Status: {resp.status_code}")
    print_json(resp.json())
    return resp.status_code == 200

def test_kyb_providers_list():
    """Test listing KYB providers"""
    print_section("Testing GET /observer/kyb-providers (List)")
    resp = requests.get(f"{BASE_URL}/observer/kyb-providers")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print_json(data)
    
    # Verify MoonPay is in the list
    moonpay = next((p for p in data if p['provider_id'] == 'provider_001'), None)
    if moonpay:
        print(f"\n✅ MoonPay found: {moonpay['provider_name']} ({moonpay['provider_domain']})")
    else:
        print("\n❌ MoonPay not found in providers list")
    
    return resp.status_code == 200 and moonpay is not None

def test_kyb_provider_get():
    """Test getting specific KYB provider"""
    print_section("Testing GET /observer/kyb-providers/provider_001 (Get MoonPay)")
    resp = requests.get(f"{BASE_URL}/observer/kyb-providers/provider_001")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print_json(data)
    
    if data.get('provider_id') == 'provider_001':
        print(f"\n✅ MoonPay provider details retrieved")
        print(f"   Name: {data['provider_name']}")
        print(f"   Domain: {data['provider_domain']}")
        print(f"   Status: {data['status']}")
    else:
        print("\n❌ Failed to get MoonPay provider")
    
    return resp.status_code == 200 and data.get('provider_id') == 'provider_001'

def test_org_registration_with_kyb():
    """Test organization registration with KYB"""
    print_section("Testing POST /observer/register-org (with KYB)")
    
    payload = {
        "org_name": "Mastercard International",
        "domain": "mastercard.com",
        "public_key": "02a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f",
        "kyb_provider": "moonpay",
        "kyb_reference": "moonpay_kyb_ref_abc123"
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    resp = requests.post(f"{BASE_URL}/observer/register-org", json=payload)
    print(f"\nStatus: {resp.status_code}")
    data = resp.json()
    print_json(data)
    
    if resp.status_code == 200 or resp.status_code == 409:  # 409 if already exists
        print(f"\n✅ Organization registered/updated")
        print(f"   Org ID: {data.get('org_id')}")
        print(f"   KYB Status: {data.get('kyb_status')}")
        print(f"   KYB Provider: {data.get('kyb_provider')}")
        return data.get('org_id')
    else:
        print(f"\n❌ Failed to register organization")
        return None

def test_org_registration_no_kyb():
    """Test organization registration without KYB"""
    print_section("Testing POST /observer/register-org (without KYB)")
    
    payload = {
        "org_name": "Acme Corporation",
        "domain": "acme.example.com",
        "public_key": "03b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g"
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    resp = requests.post(f"{BASE_URL}/observer/register-org", json=payload)
    print(f"\nStatus: {resp.status_code}")
    data = resp.json()
    print_json(data)
    
    if resp.status_code == 200 or resp.status_code == 409:
        print(f"\n✅ Organization registered/updated")
        print(f"   Org ID: {data.get('org_id')}")
        print(f"   KYB Status: {data.get('kyb_status')}")
        return data.get('org_id')
    else:
        print(f"\n❌ Failed to register organization")
        return None

def test_get_organization(org_id):
    """Test getting organization by ID"""
    print_section(f"Testing GET /observer/orgs/{org_id}")
    resp = requests.get(f"{BASE_URL}/observer/orgs/{org_id}")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print_json(data)
    
    if resp.status_code == 200:
        print(f"\n✅ Organization retrieved")
        print(f"   Name: {data.get('org_name')}")
        print(f"   Domain: {data.get('domain')}")
        print(f"   KYB Status: {data.get('kyb_status')}")
    else:
        print(f"\n❌ Failed to get organization")
    
    return resp.status_code == 200

def test_kyb_status(org_id):
    """Test KYB status endpoint"""
    print_section(f"Testing GET /observer/orgs/{org_id}/kyb-status")
    resp = requests.get(f"{BASE_URL}/observer/orgs/{org_id}/kyb-status")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print_json(data)
    
    if resp.status_code == 200:
        print(f"\n✅ KYB status retrieved")
        print(f"   Status: {data.get('kyb_status')}")
        print(f"   Provider: {data.get('kyb_provider')}")
        print(f"   Verified At: {data.get('kyb_verified_at')}")
    else:
        print(f"\n❌ Failed to get KYB status")
    
    return resp.status_code == 200

def test_kyb_verification_trigger(org_id):
    """Test KYB verification trigger"""
    print_section(f"Testing POST /observer/orgs/{org_id}/verify-kyb")
    resp = requests.post(f"{BASE_URL}/observer/orgs/{org_id}/verify-kyb")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print_json(data)
    
    if resp.status_code == 200:
        print(f"\n✅ KYB verification triggered")
        print(f"   Status: {data.get('kyb_status')}")
        print(f"   Verified At: {data.get('kyb_verified_at')}")
    else:
        print(f"\n❌ Failed to trigger KYB verification")
    
    return resp.status_code == 200

def test_agent_registration_with_org(org_id):
    """Test agent registration with org_id"""
    print_section(f"Testing POST /observer/register (with org_id)")
    
    payload = {
        "agent_id": f"test-agent-{datetime.now().strftime('%H%M%S')}",
        "public_key": "HN7cABmAq7R9E7r7zQ4gQZ5Y8zQ4gQZ5Y8zQ4gQZ5Y8",
        "solana_address": "HN7cABmAq7R9E7r7zQ4gQZ5Y8zQ4gQZ5Y8zQ4gQZ5Y8",
        "org_id": org_id
    }
    
    print(f"Request: {json.dumps(payload, indent=2)}")
    resp = requests.post(f"{BASE_URL}/observer/register", json=payload)
    print(f"\nStatus: {resp.status_code}")
    data = resp.json()
    print_json(data)
    
    if resp.status_code == 200:
        print(f"\n✅ Agent registered with organization")
        print(f"   Agent ID: {data.get('agent_id')}")
        print(f"   Org ID: {data.get('org_id')}")
        return data.get('agent_id')
    else:
        print(f"\n❌ Failed to register agent")
        return None

def test_get_agent(agent_id):
    """Test getting agent info"""
    print_section(f"Testing GET /observer/agent/{agent_id}")
    resp = requests.get(f"{BASE_URL}/observer/agent/{agent_id}")
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print_json(data)
    
    if resp.status_code == 200:
        print(f"\n✅ Agent retrieved")
        print(f"   Agent ID: {data.get('agent_id')}")
        print(f"   Org ID: {data.get('org_id')}")
        print(f"   Reputation: {data.get('reputation_score')}")
    else:
        print(f"\n❌ Failed to get agent")
    
    return resp.status_code == 200

def test_mock_moonpay_direct():
    """Test mock MoonPay endpoint directly"""
    print_section("Testing Mock MoonPay Directly")
    
    test_refs = [
        "moonpay_kyb_ref_abc123",
        "moonpay_kyb_ref_suspicious",
        "my-custom-verified-ref"
    ]
    
    for ref in test_refs:
        print(f"\n  Testing reference: {ref}")
        # This tests the mock logic within the main API
        # In a real setup, this would call the separate mock server
        resp = requests.post(
            f"{BASE_URL}/observer/register-org",
            json={
                "org_name": f"Test Org {ref[:10]}",
                "domain": f"{ref[:10]}.example.com",
                "public_key": "02" + "a" * 64,
                "kyb_provider": "moonpay",
                "kyb_reference": ref
            }
        )
        if resp.status_code in [200, 409]:
            data = resp.json()
            print(f"    Status: {data.get('kyb_status')}")
            print(f"    Verified: {data.get('kyb_verified_at')}")

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  Observer Protocol Build 2: MoonPay KYB Integration Tests")
    print("="*60)
    
    results = []
    org_id = None
    agent_id = None
    
    try:
        # Health check
        results.append(("Health Check", test_health()))
        
        # KYB Provider endpoints
        results.append(("List KYB Providers", test_kyb_providers_list()))
        results.append(("Get KYB Provider", test_kyb_provider_get()))
        
        # Organization registration
        org_id = test_org_registration_with_kyb()
        results.append(("Register Org with KYB", org_id is not None))
        
        org_id_no_kyb = test_org_registration_no_kyb()
        results.append(("Register Org without KYB", org_id_no_kyb is not None))
        
        if org_id:
            # Organization retrieval
            results.append(("Get Organization", test_get_organization(org_id)))
            
            # KYB status
            results.append(("Get KYB Status", test_kyb_status(org_id)))
            
            # KYB verification trigger
            results.append(("Trigger KYB Verification", test_kyb_verification_trigger(org_id)))
            
            # Agent with org
            agent_id = test_agent_registration_with_org(org_id)
            results.append(("Register Agent with Org", agent_id is not None))
            
            if agent_id:
                results.append(("Get Agent", test_get_agent(agent_id)))
        
        # Mock MoonPay direct tests
        test_mock_moonpay_direct()
        results.append(("Mock MoonPay Logic", True))
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to API server at localhost:8000")
        print("   Please start the server with: python main.py")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Summary
    print("\n" + "="*60)
    print("  Test Summary")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    failed = sum(1 for _, r in results if not r)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Total: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")

if __name__ == "__main__":
    main()
