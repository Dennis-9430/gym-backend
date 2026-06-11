"""Mock payment provider — simulates external payment gateway for demo/portfolio."""
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MockPaymentProvider:
    """Simulates a payment provider (Stripe/MercadoPago) for demonstration.
    
    All payments are simulated — no real transactions occur.
    Provide a complete checkout → payment → webhook flow for demo purposes.
    """
    
    def __init__(self):
        self._sessions: Dict[str, dict] = {}
    
    async def create_checkout_session(
        self,
        amount: float,
        currency: str = "USD",
        description: str = "Suscripción Gym Management",
        success_url: str = "/payments/success",
        cancel_url: str = "/payments/cancel",
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create a mock checkout session.
        
        Returns a fake session ID and checkout URL.
        The actual "payment" is simulated — no real charge occurs.
        """
        session_id = f"mock_cs_{uuid.uuid4().hex[:12]}"
        self._sessions[session_id] = {
            "id": session_id,
            "amount": amount,
            "currency": currency,
            "description": description,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "metadata": metadata or {},
        }
        
        return {
            "session_id": session_id,
            "checkout_url": f"/api/payments/mock-checkout/{session_id}",
            "amount": amount,
            "currency": currency,
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        }
    
    async def verify_payment(self, session_id: str) -> dict:
        """Verify a mock payment. Always succeeds for valid session IDs."""
        session = self._sessions.get(session_id)
        if not session:
            return {
                "verified": False,
                "status": "not_found",
                "error": "Session not found",
            }
        
        # Simulate successful payment verification
        session["status"] = "completed"
        session["paid_at"] = datetime.utcnow()
        session["payment_id"] = f"mock_pay_{uuid.uuid4().hex[:16]}"
        
        return {
            "verified": True,
            "status": "completed",
            "payment_id": session["payment_id"],
            "amount": session["amount"],
            "currency": session["currency"],
            "paid_at": session["paid_at"].isoformat(),
        }
    
    async def handle_webhook(self, payload: dict) -> dict:
        """Simulate a webhook event from the payment provider.
        
        Accepts events like:
        - {"event": "checkout.completed", "session_id": "mock_cs_..."}
        - {"event": "payment.failed", "session_id": "mock_cs_..."}
        
        Returns updated session status.
        """
        event = payload.get("event", "")
        session_id = payload.get("session_id", "")
        
        session = self._sessions.get(session_id)
        if not session:
            return {"received": True, "error": "Session not found"}
        
        if event == "checkout.completed":
            session["status"] = "completed"
            session["payment_id"] = f"mock_pay_{uuid.uuid4().hex[:16]}"
            session["paid_at"] = datetime.utcnow()
            logger.info(f"Mock webhook: checkout completed for session {session_id}")
        elif event == "payment.failed":
            session["status"] = "failed"
            logger.info(f"Mock webhook: payment failed for session {session_id}")
        else:
            logger.info(f"Mock webhook: received event {event} for session {session_id}")
        
        return {
            "received": True,
            "session_id": session_id,
            "event": event,
            "session_status": session["status"],
        }
    
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session by ID (for status checking)."""
        return self._sessions.get(session_id)


# Singleton
_provider: Optional[MockPaymentProvider] = None

def get_mock_payment_provider() -> MockPaymentProvider:
    global _provider
    if _provider is None:
        _provider = MockPaymentProvider()
    return _provider
