"""Payment router — simulated checkout and webhook endpoints.
    
Provides a mock payment flow for demo/portfolio purposes.
All payments are simulated — no real transactions occur.
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.mock_payment_provider import get_mock_payment_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["Payments"])


class CheckoutRequest(BaseModel):
    amount: float
    currency: str = "USD"
    description: str = "Suscripción Gym Management"
    success_url: str = "/payments/success"
    cancel_url: str = "/payments/cancel"


class WebhookPayload(BaseModel):
    event: str  # "checkout.completed", "payment.failed"
    session_id: str


@router.post("/checkout")
async def create_checkout(data: CheckoutRequest):
    """Create a mock checkout session.
    
    Returns a fake checkout URL. No real payment occurs.
    Use POST /api/payments/webhook to simulate payment completion.
    """
    provider = get_mock_payment_provider()
    session = await provider.create_checkout_session(
        amount=data.amount,
        currency=data.currency,
        description=data.description,
        success_url=data.success_url,
        cancel_url=data.cancel_url,
    )
    return session


@router.get("/mock-checkout/{session_id}")
async def mock_checkout_page(session_id: str):
    """Simulated checkout page redirect.
    
    In a real integration, this would be a hosted checkout page.
    Here it just returns session status and a link to complete payment.
    """
    provider = get_mock_payment_provider()
    session = provider.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session": session,
        "message": "Pago simulado — usa POST /api/payments/webhook para completar",
        "complete_url": "/api/payments/webhook",
        "payload_example": {
            "event": "checkout.completed",
            "session_id": session_id,
        },
    }


@router.post("/webhook")
async def payment_webhook(payload: WebhookPayload):
    """Simulated webhook endpoint.
    
    Accepts mock webhook events from the payment provider.
    Events:
    - checkout.completed: payment successful
    - payment.failed: payment failed
    
    In production, this would be called by Stripe/MercadoPago.
    """
    provider = get_mock_payment_provider()
    result = await provider.handle_webhook(payload.model_dump())
    return result


@router.get("/sessions/{session_id}")
async def get_session_status(session_id: str):
    """Check the status of a mock payment session."""
    provider = get_mock_payment_provider()
    session = provider.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
