"""Tests for enhanced rate limiting — store interface and middleware."""
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# ── SlidingWindowMemoryStore tests ──────────────────────────────────────────

class TestSlidingWindowMemoryStore:
    """Unit tests for the sliding window in-memory store."""

    @pytest.fixture(autouse=True)
    def fresh_store(self):
        """Create a fresh store for each test (isolation)."""
        from app.middleware.rate_limit_store import SlidingWindowMemoryStore
        self.store = SlidingWindowMemoryStore()

    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        """First request for a key is always allowed."""
        allowed, count = await self.store.check_and_increment("test:ip:1.2.3.4", 5, 60)
        assert allowed is True
        assert count == 1

    @pytest.mark.asyncio
    async def test_within_limit_returns_allowed(self):
        """Requests within the limit return allowed=True and correct count."""
        for i in range(1, 4):
            allowed, count = await self.store.check_and_increment("test:ip:1.2.3.4", 5, 60)
            assert allowed is True
            assert count == i  # 1st call → 1, 2nd → 2, 3rd → 3

    @pytest.mark.asyncio
    async def test_exceeds_limit_returns_blocked(self):
        """When count >= limit, returns allowed=False."""
        for _ in range(5):
            await self.store.check_and_increment("test:ip:1.2.3.4", 5, 60)

        allowed, count = await self.store.check_and_increment("test:ip:1.2.3.4", 5, 60)
        assert allowed is False
        assert count == 5

    @pytest.mark.asyncio
    async def test_sliding_window_expires_old_entries(self):
        """Entries outside the window are cleaned, freeing up the limit."""
        now = time.time()

        with patch("time.time", return_value=now):
            for _ in range(5):
                await self.store.check_and_increment("test:ip:1.2.3.4", 5, 60)

            # At now, all 5 requests are within the window → blocked
            allowed, _ = await self.store.check_and_increment("test:ip:1.2.3.4", 5, 60)
            assert allowed is False

        # Advance time past the window
        with patch("time.time", return_value=now + 61):
            allowed, count = await self.store.check_and_increment("test:ip:1.2.3.4", 5, 60)
            assert allowed is True
            assert count == 1

    @pytest.mark.asyncio
    async def test_different_keys_are_independent(self):
        """Different rate limit keys don't interfere."""
        for _ in range(5):
            await self.store.check_and_increment("key-a", 5, 60)

        allowed_a, _ = await self.store.check_and_increment("key-a", 5, 60)
        assert allowed_a is False

        allowed_b, count_b = await self.store.check_and_increment("key-b", 5, 60)
        assert allowed_b is True
        assert count_b == 1

    @pytest.mark.asyncio
    async def test_cleanup_old_keys_removes_expired(self):
        """cleanup_old_keys removes keys with no recent activity."""
        now = time.time()
        with patch("time.time", return_value=now):
            await self.store.check_and_increment("fresh-key", 5, 60)
            await self.store.check_and_increment("stale-key", 5, 60)

        # Advance time past max_age then cleanup
        with patch("time.time", return_value=now + 7200):
            # Add activity on fresh-key but not stale-key
            await self.store.check_and_increment("fresh-key", 5, 60)

            # Cleanup with max_age=3600 (INSIDE the patched time)
            await self.store.cleanup_old_keys(max_age_seconds=3600)

        # stale-key should be gone, fresh-key should remain
        assert "stale-key" not in self.store._store
        assert "fresh-key" in self.store._store

    @pytest.mark.asyncio
    async def test_cleanup_does_not_remove_active_keys(self):
        """cleanup_old_keys preserves keys with recent activity."""
        now = time.time()
        with patch("time.time", return_value=now):
            await self.store.check_and_increment("active-key", 5, 60)
            await self.store.check_and_increment("active-key-2", 5, 60)

        # Advance slightly but not past max_age
        with patch("time.time", return_value=now + 1800):
            await self.store.cleanup_old_keys(max_age_seconds=3600)

        # Both should still be present
        assert "active-key" in self.store._store
        assert "active-key-2" in self.store._store

    @pytest.mark.asyncio
    async def test_limit_of_one_allows_single_request(self):
        """limit=1 allows exactly one request then blocks."""
        allowed1, count1 = await self.store.check_and_increment("key:single", 1, 60)
        assert allowed1 is True
        assert count1 == 1

        allowed2, count2 = await self.store.check_and_increment("key:single", 1, 60)
        assert allowed2 is False
        assert count2 == 1

    @pytest.mark.asyncio
    async def test_partial_sliding_window(self):
        """Sliding window allows new requests as old ones expire partially."""
        now = time.time()

        with patch("time.time", return_value=now):
            # Fill: 3 requests at time 0
            for _ in range(3):
                await self.store.check_and_increment("key:partial", 3, 10)

            # Blocked
            allowed, _ = await self.store.check_and_increment("key:partial", 3, 10)
            assert allowed is False

        # Advance by 5 seconds — only the oldest entries are still within window
        # Window is 10 seconds, so entries from time 0 are now at age 5 (within window)
        # But we're still at 3 requests, so blocked
        with patch("time.time", return_value=now + 5):
            allowed, _ = await self.store.check_and_increment("key:partial", 3, 10)
            assert allowed is False

        # Advance by 11 seconds — all entries from time 0 are now outside window
        with patch("time.time", return_value=now + 11):
            allowed, count = await self.store.check_and_increment("key:partial", 3, 10)
            assert allowed is True
            assert count == 1  # fresh start

    @pytest.mark.asyncio
    async def test_zero_limit_blocks_immediately(self):
        """limit=0 blocks every request."""
        allowed, count = await self.store.check_and_increment("key:zero", 0, 60)
        assert allowed is False
        assert count == 0

    @pytest.mark.asyncio
    async def test_different_keys_different_windows(self):
        """Different keys can have independent window sizes."""
        # Small window for key-a: 2 requests in 5 seconds
        # Large window for key-b: 100 requests in 1 hour
        a1, _ = await self.store.check_and_increment("key:short", 2, 5)
        b1, _ = await self.store.check_and_increment("key:long", 100, 3600)
        assert a1 is True and b1 is True


# ── RateLimitMiddleware tests ───────────────────────────────────────────────

@pytest.mark.asyncio
class TestRateLimitMiddleware:
    """Integration tests for the new RateLimitMiddleware."""

    @pytest.fixture(autouse=True)
    def reset_store(self):
        """Reset the global store before each test."""
        from app.middleware.rate_limit import set_store
        from app.middleware.rate_limit_store import SlidingWindowMemoryStore
        set_store(SlidingWindowMemoryStore())

    @pytest.fixture
    def test_app(self):
        """Minimal FastAPI app with rate limit middleware (no constructor args)."""
        from app.middleware.rate_limit import RateLimitMiddleware
        from app.middleware.rate_limit_store import SlidingWindowMemoryStore

        api = FastAPI()
        api.add_middleware(RateLimitMiddleware)

        @api.get("/api/tenants/login")
        async def login():
            return {"ok": True}

        @api.get("/api/tenants/register")
        async def register():
            return {"ok": True}

        @api.get("/api/tenants/forgot-password")
        async def forgot_password():
            return {"ok": True}

        @api.get("/api/tenants/reset-password")
        async def reset_password():
            return {"ok": True}

        @api.get("/api/some-other-route")
        async def other_route():
            return {"ok": True}

        @api.get("/health")
        async def health():
            return {"status": "healthy"}

        @api.get("/docs")
        async def docs():
            return {"docs": "here"}

        @api.get("/")
        async def root():
            return {"message": "root"}

        @api.get("/redoc")
        async def redoc():
            return {"redoc": "here"}

        @api.get("/openapi.json")
        async def openapi():
            return {"openapi": "3.0"}

        return api

    async def test_exempt_paths_are_not_rate_limited(self, test_app):
        """Exempt paths (/, /health, /docs, /openapi.json, /redoc) bypass rate limit."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            # Hit /health many times — should never get 429
            for _ in range(10):
                resp = await client.get("/health")
                assert resp.status_code == 200

            resp = await client.get("/docs")
            assert resp.status_code == 200

    async def test_endpoint_specific_rule_login_blocks_after_5(self, test_app):
        """Login endpoint blocks after 5 requests per IP."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            for i in range(5):
                resp = await client.get("/api/tenants/login")
                assert resp.status_code == 200, f"Request {i+1} should be allowed"

            resp = await client.get("/api/tenants/login")
            assert resp.status_code == 429
            data = resp.json()
            assert "Demasiadas solicitudes" in data["error"]["detail"]

    async def test_endpoint_specific_rule_register_blocks_after_5(self, test_app):
        """Register endpoint blocks after 5 requests per hour per IP."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            for i in range(5):
                resp = await client.get("/api/tenants/register")
                assert resp.status_code == 200, f"Request {i+1} should be allowed"

            resp = await client.get("/api/tenants/register")
            assert resp.status_code == 429

    async def test_endpoint_specific_rule_forgot_password_blocks_after_3(self, test_app):
        """Forgot password blocks after 3 requests per IP."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            for i in range(3):
                resp = await client.get("/api/tenants/forgot-password")
                assert resp.status_code == 200, f"Request {i+1} should be allowed"

            resp = await client.get("/api/tenants/forgot-password")
            assert resp.status_code == 429

    async def test_endpoint_specific_rule_reset_password_blocks_after_5(self, test_app):
        """Reset password blocks after 5 requests per IP."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            for i in range(5):
                resp = await client.get("/api/tenants/reset-password")
                assert resp.status_code == 200, f"Request {i+1} should be allowed"

            resp = await client.get("/api/tenants/reset-password")
            assert resp.status_code == 429

    async def test_default_rate_limit_for_other_routes(self, test_app):
        """Non-endpoint-specific routes use the default 2000/min rate limit."""
        # Temporarily reduce default limit via the store to test
        from app.middleware.rate_limit import DEFAULT_RATE_LIMIT, DEFAULT_WINDOW, get_store

        store = get_store()
        # Fill up the default limit for this IP
        client_ip = "127.0.0.1"
        for _ in range(2000):
            allowed, _ = await store.check_and_increment(f"default:{client_ip}", 2000, 60)
            if not allowed:
                break

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/api/some-other-route")
            assert resp.status_code == 429

    async def test_options_requests_bypass_rate_limit(self, test_app):
        """OPTIONS requests are not rate limited."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.options("/api/tenants/login")
            assert resp.status_code in (200, 405)  # 405 means method not allowed, but no 429

    async def test_different_ips_have_independent_limits(self, test_app):
        """Different client IPs have independent rate limits."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            # Use IP 1.2.3.4 for login
            for _ in range(5):
                resp = await client.get("/api/tenants/login", headers={"X-Forwarded-For": "1.2.3.4"})
                assert resp.status_code == 200

            # IP 1.2.3.4 should now be blocked for login
            resp = await client.get("/api/tenants/login", headers={"X-Forwarded-For": "1.2.3.4"})
            assert resp.status_code == 429

            # Different IP 5.6.7.8 should still be allowed
            resp = await client.get("/api/tenants/login", headers={"X-Forwarded-For": "5.6.7.8"})
            assert resp.status_code == 200

    async def test_exempt_path_redoc(self, test_app):
        """/redoc is exempt from rate limiting."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            for _ in range(10):
                resp = await client.get("/redoc")
                assert resp.status_code == 200

    async def test_root_path_exempt(self, test_app):
        """Root path / is exempt from rate limiting."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            for _ in range(10):
                resp = await client.get("/")
                assert resp.status_code == 200

    async def test_default_route_still_allows_within_limit(self, test_app):
        """Default rate-limited routes allow requests within the 2000/min limit."""
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            for _ in range(5):
                resp = await client.get("/api/some-other-route")
                assert resp.status_code == 200


# ── Main.py integration tests ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestRateLimitMainIntegration:
    """Tests that main.py correctly registers the new middleware."""

    @pytest.fixture(autouse=True)
    def reset_store(self):
        """Reset the global store before each test."""
        from app.middleware.rate_limit import set_store
        from app.middleware.rate_limit_store import SlidingWindowMemoryStore
        set_store(SlidingWindowMemoryStore())

    async def test_middleware_registered_without_constructor_args(self):
        """The RateLimitMiddleware in main.py is registered without constructor args."""
        from app.main import app
        # Find RateLimitMiddleware in the user middleware chain
        middlewares = [m for m in app.user_middleware if m.cls.__name__ == "RateLimitMiddleware"]
        assert len(middlewares) == 1, "RateLimitMiddleware should be registered exactly once"
        middleware = middlewares[0]
        # The new middleware should NOT have a `rate_limit` kwarg
        # It should only have the `app` arg which is added automatically by add_middleware
        assert "rate_limit" not in middleware.kwargs, (
            "New RateLimitMiddleware should not use rate_limit constructor arg"
        )

    async def test_rate_limit_store_module_importable(self):
        """The new rate_limit_store module can be imported without errors."""
        from app.middleware.rate_limit_store import RateLimitStore, SlidingWindowMemoryStore
        assert RateLimitStore is not None
        assert SlidingWindowMemoryStore is not None

    async def test_old_rate_limit_store_not_used(self):
        """The old _rate_limit_store module variable should not be referenced."""
        import app.middleware.rate_limit as rl
        # The module should not have _rate_limit_store anymore
        assert not hasattr(rl, "_rate_limit_store"), (
            "Old _rate_limit_store should be removed"
        )

    async def test_old_check_rate_limit_not_used(self):
        """The old check_rate_limit function should not exist."""
        import app.middleware.rate_limit as rl
        assert not hasattr(rl, "check_rate_limit"), (
            "Old check_rate_limit function should be removed"
        )

    async def test_old_login_rate_limit_constant_removed(self):
        """The old LOGIN_RATE_LIMIT constant should be removed."""
        import app.middleware.rate_limit as rl
        assert not hasattr(rl, "LOGIN_RATE_LIMIT"), (
            "Old LOGIN_RATE_LIMIT constant should be removed"
        )
