#!/usr/bin/env python3
"""
Mock MoonPay KYB Verification Server (Build 2d)

This is a mock implementation of the MoonPay KYB verification endpoint
for development and testing purposes.

In production, Observer Protocol will call the real MoonPay API.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import uvicorn

app = FastAPI(
    title="Mock MoonPay KYB API",
    description="Mock implementation of MoonPay KYB verification for Observer Protocol testing",
    version="1.0.0"
)


class KYBVerificationResponse(BaseModel):
    reference: str
    verified: bool
    entity_name: Optional[str]
    verified_at: Optional[str]


# Mock database of known KYB references
MOCK_KYB_DB = {
    "moonpay_kyb_ref_abc123": {
        "entity_name": "Mastercard International",
        "verified": True,
        "verified_at": "2026-03-24T00:00:00Z"
    },
    "moonpay_kyb_ref_acme456": {
        "entity_name": "Acme Corporation", 
        "verified": True,
        "verified_at": "2026-03-20T00:00:00Z"
    },
    "moonpay_kyb_ref_suspicious": {
        "entity_name": "Suspicious Entity LLC",
        "verified": False,
        "verified_at": None
    }
}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "mock-moonpay-kyb",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/kyb/verify/{reference}", response_model=KYBVerificationResponse)
async def verify_kyb(reference: str):
    """
    Mock KYB verification endpoint
    
    Path parameters:
    - reference: The KYB reference ID to verify
    
    Returns:
    - verified: true/false
    - entity_name: Name of the verified entity
    - verified_at: ISO timestamp of verification
    
    Mock logic:
    - References containing 'verified' or in MOCK_KYB_DB return verified=true
    - References containing 'rejected' return verified=false
    - All others return verified=true (assume valid reference format)
    """
    # Check mock database first
    if reference in MOCK_KYB_DB:
        entry = MOCK_KYB_DB[reference]
        return KYBVerificationResponse(
            reference=reference,
            verified=entry["verified"],
            entity_name=entry["entity_name"],
            verified_at=entry["verified_at"]
        )
    
    # Dynamic mock logic for unknown references
    is_verified = "rejected" not in reference.lower() and "suspicious" not in reference.lower()
    
    # Extract entity name from reference (mock logic)
    entity_name = "Unknown Entity"
    if "mastercard" in reference.lower():
        entity_name = "Mastercard International"
    elif "acme" in reference.lower():
        entity_name = "Acme Corporation"
    elif "futurebit" in reference.lower():
        entity_name = "FutureBit LLC"
    elif "arcadia" in reference.lower():
        entity_name = "Arcadia Labs"
    else:
        entity_name = f"Organization ({reference[:8]}...)"
    
    return KYBVerificationResponse(
        reference=reference,
        verified=is_verified,
        entity_name=entity_name,
        verified_at=datetime.now(timezone.utc).isoformat() if is_verified else None
    )


@app.get("/kyb/verify")
async def verify_kyb_query(reference: str):
    """Alternative endpoint using query parameter"""
    return await verify_kyb(reference)


if __name__ == "__main__":
    print("🚀 Starting Mock MoonPay KYB Server on http://localhost:8001")
    print("📋 Endpoints:")
    print("   GET /health          - Health check")
    print("   GET /kyb/verify/{ref} - Verify KYB reference")
    print("")
    print("🧪 Test references:")
    print("   moonpay_kyb_ref_abc123  -> Mastercard International (verified)")
    print("   moonpay_kyb_ref_acme456 -> Acme Corporation (verified)")
    print("   moonpay_kyb_ref_suspicious -> Suspicious Entity (rejected)")
    print("   any-rejected-ref        -> Rejected")
    print("   any-other-ref           -> Verified (default)")
    uvicorn.run(app, host="0.0.0.0", port=8001)
