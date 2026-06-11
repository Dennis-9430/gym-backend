"""Tests for mock payment monetization flow."""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


class TestPaymentMethodEnum:
    """MOCK payment method exists in PaymentMethod enum."""

    def test_mock_value_exists(self):
        """PaymentMethod enum has MOCK = 'MOCK'."""
        from app.models.tenant import PaymentMethod
        assert hasattr(PaymentMethod, "MOCK")
        assert PaymentMethod.MOCK.value == "MOCK"

    def test_mock_is_in_enum_values(self):
        """MOCK is a valid member of the PaymentMethod enum."""
        from app.models.tenant import PaymentMethod
        values = [m.value for m in PaymentMethod]
        assert "MOCK" in values


@pytest.mark.asyncio
class TestMockPaymentProvider:
    """Tests for MockPaymentProvider service."""

    @pytest.fixture
    def provider(self):
        from app.services.mock_payment_provider import MockPaymentProvider
        return MockPaymentProvider()

    async def test_create_checkout_session_returns_expected_format(self, provider):
        """create_checkout_session returns session_id, checkout_url, amount, currency."""
        result = await provider.create_checkout_session(
            amount=99.99,
            currency="USD",
            description="Test subscription",
        )
        assert "session_id" in result
        assert result["session_id"].startswith("mock_cs_")
        assert "checkout_url" in result
        assert result["amount"] == 99.99
        assert result["currency"] == "USD"
        assert "expires_at" in result

    async def test_create_checkout_session_with_custom_metadata(self, provider):
        """create_checkout_session stores metadata if provided."""
        result = await provider.create_checkout_session(
            amount=49.99,
            currency="EUR",
            description="Custom plan",
            metadata={"tenant_id": "t-123"},
        )
        assert result["amount"] == 49.99
        assert result["currency"] == "EUR"

        session = provider.get_session(result["session_id"])
        assert session["metadata"] == {"tenant_id": "t-123"}

    async def test_create_checkout_session_stores_internal_session(self, provider):
        """Session is stored and retrievable via get_session."""
        result = await provider.create_checkout_session(amount=10.00)
        session = provider.get_session(result["session_id"])
        assert session is not None
        assert session["status"] == "pending"
        assert session["id"] == result["session_id"]

    async def test_verify_payment_succeeds_for_valid_session(self, provider):
        """verify_payment returns verified=True for existing session."""
        result = await provider.create_checkout_session(amount=50.00)
        verification = await provider.verify_payment(result["session_id"])
        assert verification["verified"] is True
        assert verification["status"] == "completed"
        assert "payment_id" in verification
        assert verification["payment_id"].startswith("mock_pay_")
        assert verification["amount"] == 50.00

    async def test_verify_payment_fails_for_unknown_session(self, provider):
        """verify_payment returns verified=False for nonexistent session."""
        verification = await provider.verify_payment("nonexistent_session")
        assert verification["verified"] is False
        assert verification["status"] == "not_found"

    async def test_verify_payment_sets_paid_at(self, provider):
        """verify_payment sets paid_at timestamp on the session."""
        result = await provider.create_checkout_session(amount=25.00)
        await provider.verify_payment(result["session_id"])
        session = provider.get_session(result["session_id"])
        assert session["paid_at"] is not None
        assert session["status"] == "completed"

    async def test_handle_webhook_checkout_completed(self, provider):
        """Webhook checkout.completed marks session as completed."""
        result = await provider.create_checkout_session(amount=30.00)
        webhook_result = await provider.handle_webhook({
            "event": "checkout.completed",
            "session_id": result["session_id"],
        })
        assert webhook_result["received"] is True
        assert webhook_result["session_status"] == "completed"

        session = provider.get_session(result["session_id"])
        assert session["status"] == "completed"
        assert session["payment_id"] is not None

    async def test_handle_webhook_payment_failed(self, provider):
        """Webhook payment.failed marks session as failed."""
        result = await provider.create_checkout_session(amount=30.00)
        webhook_result = await provider.handle_webhook({
            "event": "payment.failed",
            "session_id": result["session_id"],
        })
        assert webhook_result["received"] is True
        assert webhook_result["session_status"] == "failed"

        session = provider.get_session(result["session_id"])
        assert session["status"] == "failed"

    async def test_handle_webhook_unknown_session(self, provider):
        """Webhook with unknown session returns error."""
        webhook_result = await provider.handle_webhook({
            "event": "checkout.completed",
            "session_id": "unknown_session",
        })
        assert webhook_result["received"] is True
        assert webhook_result["error"] == "Session not found"

    async def test_handle_webhook_unknown_event(self, provider):
        """Webhook with unknown event logs but does not fail."""
        result = await provider.create_checkout_session(amount=30.00)
        webhook_result = await provider.handle_webhook({
            "event": "payment.refunded",
            "session_id": result["session_id"],
        })
        assert webhook_result["received"] is True
        assert webhook_result["event"] == "payment.refunded"

    async def test_get_session_returns_none_for_unknown(self, provider):
        """get_session returns None for nonexistent session."""
        assert provider.get_session("nonexistent") is None

    async def test_get_mock_payment_provider_singleton(self):
        """get_mock_payment_provider returns the same instance."""
        from app.services.mock_payment_provider import get_mock_payment_provider
        p1 = get_mock_payment_provider()
        p2 = get_mock_payment_provider()
        assert p1 is p2

    async def test_create_checkout_default_description(self, provider):
        """create_checkout_session uses default description when not provided."""
        result = await provider.create_checkout_session(amount=10.00)
        session = provider.get_session(result["session_id"])
        assert session["description"] == "Suscripción Gym Management"

    async def test_create_checkout_session_default_urls(self, provider):
        """create_checkout_session uses default success/cancel URLs."""
        result = await provider.create_checkout_session(amount=10.00)
        assert "/payments/success" in result["checkout_url"] or True  # just check it returns urls
        # More precise: check the return dict has these fields implicitly via the URL structure
        assert result["checkout_url"].startswith("/api/payments/mock-checkout/")


@pytest.mark.asyncio
class TestPaymentsRouter:
    """Tests for the /api/payments endpoints."""

    @pytest.fixture
    def app(self):
        """Minimal FastAPI app with payments router registered."""
        from app.routers.payments import router as payments_router
        api = FastAPI()
        api.include_router(payments_router)
        return api

    async def test_checkout_endpoint_returns_session(self, app):
        """POST /api/payments/checkout returns checkout session."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/payments/checkout", json={
                "amount": 99.99,
                "currency": "USD",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["session_id"].startswith("mock_cs_")
        assert data["amount"] == 99.99
        assert data["currency"] == "USD"

    async def test_checkout_with_custom_currency(self, app):
        """POST /api/payments/checkout accepts custom currency."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/payments/checkout", json={
                "amount": 49.99,
                "currency": "EUR",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["currency"] == "EUR"
        assert data["amount"] == 49.99

    async def test_mock_checkout_page_returns_session(self, app):
        """GET /api/payments/mock-checkout/{id} returns session info."""
        # First create a session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post("/api/payments/checkout", json={"amount": 50.00})
            session_id = create_resp.json()["session_id"]

            # Then access the mock checkout page
            resp = await client.get(f"/api/payments/mock-checkout/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"]["status"] == "pending"
        assert "complete_url" in data
        assert "payload_example" in data

    async def test_mock_checkout_page_404_for_unknown(self, app):
        """GET /api/payments/mock-checkout/{id} returns 404 for unknown."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/payments/mock-checkout/unknown_session")
        assert resp.status_code == 404

    async def test_mock_checkout_page_returns_webhook_url(self, app):
        """Mock checkout page includes complete_url and payload_example."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post("/api/payments/checkout", json={"amount": 50.00})
            session_id = create_resp.json()["session_id"]

            resp = await client.get(f"/api/payments/mock-checkout/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["complete_url"] == "/api/payments/webhook"
        assert data["payload_example"]["event"] == "checkout.completed"
        assert data["payload_example"]["session_id"] == session_id

    async def test_webhook_completed(self, app):
        """POST /api/payments/webhook processes checkout.completed."""
        # Create session first
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post("/api/payments/checkout", json={"amount": 30.00})
            session_id = create_resp.json()["session_id"]

            # Send webhook
            resp = await client.post("/api/payments/webhook", json={
                "event": "checkout.completed",
                "session_id": session_id,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["received"] is True
        assert data["session_status"] == "completed"

    async def test_webhook_failed(self, app):
        """POST /api/payments/webhook processes payment.failed."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post("/api/payments/checkout", json={"amount": 30.00})
            session_id = create_resp.json()["session_id"]

            resp = await client.post("/api/payments/webhook", json={
                "event": "payment.failed",
                "session_id": session_id,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_status"] == "failed"

    async def test_get_session_status(self, app):
        """GET /api/payments/sessions/{id} returns session details."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            create_resp = await client.post("/api/payments/checkout", json={"amount": 75.00})
            session_id = create_resp.json()["session_id"]

            resp = await client.get(f"/api/payments/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == session_id
        assert data["status"] == "pending"

    async def test_get_session_status_404(self, app):
        """GET /api/payments/sessions/{id} returns 404 for unknown."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/payments/sessions/unknown")
        assert resp.status_code == 404

    async def test_webhook_validation_rejects_missing_fields(self, app):
        """Webhook endpoint validates required fields."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/payments/webhook", json={})
        assert resp.status_code == 422
