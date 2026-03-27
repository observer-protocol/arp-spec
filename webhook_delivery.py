#!/usr/bin/env python3
"""
Webhook Delivery System for Observer Protocol
Fix #10: Webhook notifications on VAC revocation

This module provides webhook delivery capabilities for the Observer Protocol,
notifying partners and other interested parties when events like VAC revocation occur.

Features:
- Asynchronous webhook delivery
- Retry logic with exponential backoff
- Delivery tracking and status monitoring
- HMAC signature verification for security
- Support for multiple webhook events

Environment Variables:
    OP_WEBHOOK_TIMEOUT: Request timeout in seconds (default: 10)
    OP_WEBHOOK_MAX_RETRIES: Maximum retry attempts (default: 3)
    OP_WEBHOOK_SECRET: Secret key for HMAC signatures
    OP_WEBHOOK_RETRY_DELAY: Initial retry delay in seconds (default: 1)
"""

import os
import json
import hmac
import hashlib
import base64
import asyncio
from datetime import datetime

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum


class WebhookEventType(Enum):
    """Types of webhook events."""
    VAC_REVOKED = "vac.revoked"
    VAC_ISSUED = "vac.issued"
    VAC_REFRESHED = "vac.refreshed"
    ATTESTATION_ISSUED = "attestation.issued"
    ATTESTATION_REVOKED = "attestation.revoked"
    AGENT_VERIFIED = "agent.verified"
    PARTNER_REGISTERED = "partner.registered"


class WebhookStatus(Enum):
    """Status of webhook delivery attempts."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class WebhookPayload:
    """Structure for webhook payloads."""
    event_type: str
    timestamp: str
    data: Dict[str, Any]
    webhook_id: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "webhook_id": self.webhook_id,
            "data": self.data
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'))


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt."""
    delivery_id: str
    webhook_id: str
    event_type: str
    url: str
    payload: str
    status: str
    created_at: str
    delivered_at: Optional[str] = None
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0


class WebhookSigner:
    """Handles HMAC signing of webhook payloads."""
    
    def __init__(self, secret: Optional[str] = None):
        self.secret = secret or os.environ.get('OP_WEBHOOK_SECRET', '')
    
    def sign(self, payload: str) -> str:
        """Sign a payload with HMAC-SHA256."""
        if not self.secret:
            return ""
        
        signature = hmac.new(
            self.secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).digest()
        
        return base64.b64encode(signature).decode()
    
    def verify(self, payload: str, signature: str) -> bool:
        """Verify a payload signature."""
        expected = self.sign(payload)
        return hmac.compare_digest(expected, signature)


class WebhookDeliverer:
    """
    Handles delivery of webhooks to registered endpoints.
    
    This class manages the queue, delivery, and retry logic for webhooks.
    """
    
    def __init__(
        self,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None
    ):
        self.timeout = timeout or int(os.environ.get('OP_WEBHOOK_TIMEOUT', '10'))
        self.max_retries = max_retries or int(os.environ.get('OP_WEBHOOK_MAX_RETRIES', '3'))
        self.retry_delay = retry_delay or float(os.environ.get('OP_WEBHOOK_RETRY_DELAY', '1'))
        self.signer = WebhookSigner()
        self._delivery_history: List[WebhookDelivery] = []
    
    async def send_webhook(
        self,
        url: str,
        payload: WebhookPayload,
        headers: Optional[Dict[str, str]] = None
    ) -> WebhookDelivery:
        """
        Send a webhook to the specified URL.
        
        Args:
            url: The webhook endpoint URL
            payload: The webhook payload
            headers: Additional headers to include
            
        Returns:
            WebhookDelivery record of the attempt
        """
        import uuid
        
        delivery_id = str(uuid.uuid4())
        payload_json = payload.to_json()
        signature = self.signer.sign(payload_json)
        
        # Build headers
        request_headers = {
            'Content-Type': 'application/json',
            'X-Webhook-ID': payload.webhook_id,
            'X-Event-Type': payload.event_type,
            'X-Delivery-ID': delivery_id,
            'X-Signature': signature,
            'User-Agent': 'ObserverProtocol-Webhook/1.0'
        }
        
        if headers:
            request_headers.update(headers)
        
        # Create delivery record
        delivery = WebhookDelivery(
            delivery_id=delivery_id,
            webhook_id=payload.webhook_id,
            event_type=payload.event_type,
            url=url,
            payload=payload_json,
            status=WebhookStatus.PENDING.value,
            created_at=datetime.utcnow().isoformat()
        )
        
        # Check if aiohttp is available
        if not AIOHTTP_AVAILABLE:
            delivery.status = WebhookStatus.FAILED.value
            delivery.error_message = "aiohttp not installed - webhook delivery disabled"
            self._delivery_history.append(delivery)
            return delivery
        
        # Attempt delivery
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=payload_json,
                    headers=request_headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    delivery.response_status = response.status
                    delivery.response_body = await response.text()
                    
                    if response.status >= 200 and response.status < 300:
                        delivery.status = WebhookStatus.DELIVERED.value
                        delivery.delivered_at = datetime.utcnow().isoformat()
                    else:
                        delivery.status = WebhookStatus.FAILED.value
                        delivery.error_message = f"HTTP {response.status}"
                        
        except asyncio.TimeoutError:
            delivery.status = WebhookStatus.FAILED.value
            delivery.error_message = "Request timeout"
        except Exception as e:
            delivery.status = WebhookStatus.FAILED.value
            delivery.error_message = str(e)
        
        self._delivery_history.append(delivery)
        return delivery
    
    async def send_with_retry(
        self,
        url: str,
        payload: WebhookPayload,
        headers: Optional[Dict[str, str]] = None
    ) -> WebhookDelivery:
        """
        Send a webhook with retry logic.
        
        Implements exponential backoff for retries.
        """
        delivery = None
        
        for attempt in range(self.max_retries + 1):
            delivery = await self.send_webhook(url, payload, headers)
            
            if delivery.status == WebhookStatus.DELIVERED.value:
                return delivery
            
            if attempt < self.max_retries:
                delivery.status = WebhookStatus.RETRYING.value
                delivery.retry_count = attempt + 1
                
                # Exponential backoff
                delay = self.retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)
        
        # All retries exhausted
        if delivery:
            delivery.status = WebhookStatus.FAILED.value
        
        return delivery
    
    def get_delivery_history(
        self,
        webhook_id: Optional[str] = None,
        event_type: Optional[str] = None
    ) -> List[WebhookDelivery]:
        """Get delivery history with optional filtering."""
        history = self._delivery_history
        
        if webhook_id:
            history = [d for d in history if d.webhook_id == webhook_id]
        
        if event_type:
            history = [d for d in history if d.event_type == event_type]
        
        return history


class WebhookRegistry:
    """
    Registry for managing webhook endpoints and delivering events.
    
    Integrates with the database to persist webhook registrations
    and delivery status.
    """
    
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.environ.get(
            'DATABASE_URL',
            'postgresql://agentic_terminal:at_secure_2026@localhost/agentic_terminal_db'
        )
        self.deliverer = WebhookDeliverer()
    
    def _get_db_connection(self):
        """Get database connection."""
        import psycopg2
        return psycopg2.connect(self.db_url)
    
    def register_webhook(
        self,
        entity_id: str,
        entity_type: str,  # 'partner', 'agent', 'organization'
        url: str,
        events: List[str],
        secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a new webhook endpoint.
        
        Args:
            entity_id: ID of the entity registering the webhook
            entity_type: Type of entity ('partner', 'agent', 'organization')
            url: The webhook URL
            events: List of event types to subscribe to
            secret: Optional secret for HMAC signatures
            
        Returns:
            Dict with webhook registration details
        """
        import uuid
        
        webhook_id = str(uuid.uuid4())
        
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO webhook_registry (
                    webhook_id, entity_id, entity_type, url, 
                    events, secret, is_active, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                RETURNING webhook_id, created_at
            """, (
                webhook_id, entity_id, entity_type, url,
                json.dumps(events), secret, True
            ))
            
            result = cursor.fetchone()
            conn.commit()
            
            return {
                "webhook_id": result[0],
                "entity_id": entity_id,
                "entity_type": entity_type,
                "url": url,
                "events": events,
                "created_at": result[1].isoformat() if result[1] else None
            }
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
    
    def get_webhooks_for_event(
        self,
        event_type: str,
        entity_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all webhooks subscribed to a specific event."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT webhook_id, entity_id, entity_type, url, events, secret
                FROM webhook_registry
                WHERE is_active = TRUE
                  AND events @> %s
            """
            params = [json.dumps([event_type])]
            
            if entity_id:
                query += " AND entity_id = %s"
                params.append(entity_id)
            
            cursor.execute(query, params)
            
            webhooks = []
            for row in cursor.fetchall():
                webhooks.append({
                    "webhook_id": row[0],
                    "entity_id": row[1],
                    "entity_type": row[2],
                    "url": row[3],
                    "events": json.loads(row[4]),
                    "secret": row[5]
                })
            
            return webhooks
            
        finally:
            cursor.close()
            conn.close()
    
    async def notify_vac_revoked(
        self,
        credential_id: str,
        agent_id: str,
        reason: str,
        revoked_by: Optional[str] = None
    ) -> List[WebhookDelivery]:
        """
        Notify all relevant webhooks when a VAC is revoked.
        
        This is the main entry point for Fix #10.
        
        Args:
            credential_id: The revoked credential ID
            agent_id: The agent whose VAC was revoked
            reason: Reason for revocation
            revoked_by: Optional ID of entity that revoked
            
        Returns:
            List of delivery records
        """
        import uuid
        
        # Build payload
        payload = WebhookPayload(
            event_type=WebhookEventType.VAC_REVOKED.value,
            timestamp=datetime.utcnow().isoformat(),
            data={
                "credential_id": credential_id,
                "agent_id": agent_id,
                "reason": reason,
                "revoked_by": revoked_by,
                "revoked_at": datetime.utcnow().isoformat()
            },
            webhook_id=str(uuid.uuid4())
        )
        
        # Find relevant webhooks
        # Notify: agent, partner who may have attested, and OP
        webhooks = []
        webhooks.extend(self.get_webhooks_for_event(
            WebhookEventType.VAC_REVOKED.value,
            entity_id=agent_id
        ))
        
        # Get partner webhooks if revoked_by is a partner
        if revoked_by:
            webhooks.extend(self.get_webhooks_for_event(
                WebhookEventType.VAC_REVOKED.value,
                entity_id=revoked_by
            ))
        
        # Deliver to all unique URLs
        deliveries = []
        seen_urls = set()
        
        for webhook in webhooks:
            if webhook['url'] in seen_urls:
                continue
            seen_urls.add(webhook['url'])
            
            # Use custom signer if webhook has secret
            if webhook.get('secret'):
                self.deliverer.signer = WebhookSigner(webhook['secret'])
            
            delivery = await self.deliverer.send_with_retry(
                url=webhook['url'],
                payload=payload
            )
            deliveries.append(delivery)
            
            # Record delivery in database
            self._record_delivery(delivery, webhook['webhook_id'])
        
        return deliveries
    
    def _record_delivery(self, delivery: WebhookDelivery, webhook_id: str):
        """Record a delivery attempt in the database."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO webhook_deliveries (
                    delivery_id, webhook_id, event_type, url,
                    payload, status, response_status, response_body,
                    error_message, retry_count, created_at, delivered_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                delivery.delivery_id, webhook_id, delivery.event_type,
                delivery.url, delivery.payload, delivery.status,
                delivery.response_status, delivery.response_body,
                delivery.error_message, delivery.retry_count,
                delivery.created_at, delivery.delivered_at
            ))
            
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"Failed to record delivery: {e}")
        finally:
            cursor.close()
            conn.close()


# Convenience functions

async def notify_revocation(
    credential_id: str,
    agent_id: str,
    reason: str,
    revoked_by: Optional[str] = None
) -> List[WebhookDelivery]:
    """
    Convenience function to notify webhooks of a VAC revocation.
    
    Usage:
        from webhook_delivery import notify_revocation
        
        deliveries = await notify_revocation(
            credential_id="vac_123",
            agent_id="agent_456",
            reason="compromise",
            revoked_by="partner_789"
        )
    """
    registry = WebhookRegistry()
    return await registry.notify_vac_revoked(
        credential_id=credential_id,
        agent_id=agent_id,
        reason=reason,
        revoked_by=revoked_by
    )


def create_webhook_table_sql() -> str:
    """
    SQL to create the webhook registry table.
    
    Run this migration to enable webhook functionality.
    """
    return """
    -- Webhook Registry Table
    CREATE TABLE IF NOT EXISTS webhook_registry (
        webhook_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        entity_id TEXT NOT NULL,
        entity_type TEXT NOT NULL CHECK (entity_type IN ('partner', 'agent', 'organization')),
        url TEXT NOT NULL,
        events JSONB NOT NULL DEFAULT '[]',
        secret TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    
    CREATE INDEX idx_webhook_registry_entity ON webhook_registry(entity_id, entity_type);
    CREATE INDEX idx_webhook_registry_events ON webhook_registry USING GIN(events);
    
    -- Webhook Delivery Log Table
    CREATE TABLE IF NOT EXISTS webhook_deliveries (
        delivery_id UUID PRIMARY KEY,
        webhook_id UUID REFERENCES webhook_registry(webhook_id),
        event_type TEXT NOT NULL,
        url TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL,
        response_status INTEGER,
        response_body TEXT,
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        delivered_at TIMESTAMP WITH TIME ZONE
    );
    
    CREATE INDEX idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id);
    CREATE INDEX idx_webhook_deliveries_created ON webhook_deliveries(created_at);
    """


# Integration with VAC revocation

async def on_vac_revoked(
    credential_id: str,
    agent_id: str,
    reason: str,
    revoked_by: Optional[str] = None
):
    """
    Hook to be called when a VAC is revoked.
    
    This function is called by the VAC revocation endpoint
    to trigger webhook notifications.
    
    Usage in api-server-v2.py:
        from webhook_delivery import on_vac_revoked
        
        @app.post("/vac/{credential_id}/revoke")
        def revoke_credential(...):
            # ... revoke logic ...
            
            # Notify webhooks (async)
            asyncio.create_task(on_vac_revoked(
                credential_id=credential_id,
                agent_id=agent_id,
                reason=reason,
                revoked_by=revoked_by
            ))
    """
    try:
        deliveries = await notify_revocation(
            credential_id=credential_id,
            agent_id=agent_id,
            reason=reason,
            revoked_by=revoked_by
        )
        
        # Log results
        successful = sum(1 for d in deliveries if d.status == WebhookStatus.DELIVERED.value)
        failed = len(deliveries) - successful
        
        print(f"Webhook notifications for VAC revocation:")
        print(f"  Total: {len(deliveries)}")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        
        return deliveries
        
    except Exception as e:
        print(f"Webhook notification failed: {e}")
        return []


if __name__ == "__main__":
    # Demo of webhook functionality
    print("=" * 60)
    print("Webhook Delivery System Demo (Fix #10)")
    print("=" * 60)
    
    # Show table creation SQL
    print("\n--- SQL Migration ---")
    print(create_webhook_table_sql())
    
    # Demo payload signing
    print("\n--- Webhook Signing ---")
    signer = WebhookSigner("test_secret_key")
    payload = '{"event_type":"vac.revoked","agent_id":"test"}'
    signature = signer.sign(payload)
    print(f"Payload: {payload}")
    print(f"Signature: {signature}")
    print(f"Verification: {signer.verify(payload, signature)}")
    
    print("\n--- Webhook Payload Structure ---")
    import uuid
    payload = WebhookPayload(
        event_type=WebhookEventType.VAC_REVOKED.value,
        timestamp=datetime.utcnow().isoformat(),
        data={
            "credential_id": "vac_123",
            "agent_id": "agent_456",
            "reason": "compromise"
        },
        webhook_id=str(uuid.uuid4())
    )
    print(json.dumps(payload.to_dict(), indent=2))
    
    print("\n" + "=" * 60)
    print("Fix #10: Webhook delivery on revocation - Ready")
    print("=" * 60)
