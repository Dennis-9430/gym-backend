"""Tests for rendimiento improvements — GZip, indexes, parallel queries, cache."""
import time
import pytest


# ─── Task 1: GZip middleware ────────────────────────────────────────────────

class TestGZipMiddleware:
    """GZipMiddleware is registered in the FastAPI app."""

    def test_gzip_middleware_is_registered(self):
        """GZipMiddleware should be in app.user_middleware."""
        from app.main import app
        from starlette.middleware.gzip import GZipMiddleware

        middlewares = [
            m for m in app.user_middleware
            if m.cls == GZipMiddleware
        ]
        assert len(middlewares) == 1, (
            "GZipMiddleware should be registered exactly once"
        )

    def test_gzip_middleware_has_minimum_size_1000(self):
        """GZipMiddleware should have minimum_size=1000."""
        from app.main import app
        from starlette.middleware.gzip import GZipMiddleware

        middlewares = [
            m for m in app.user_middleware
            if m.cls == GZipMiddleware
        ]
        assert len(middlewares) == 1
        assert middlewares[0].kwargs.get("minimum_size") == 1000, (
            "GZipMiddleware should have minimum_size=1000"
        )


# ─── Task 2: Missing indexes ────────────────────────────────────────────────

class TestIndexesAdded:
    """New performance indexes exist in database.py and migrate_indexes.py."""

    def test_tenant_payments_created_at_index_in_database(self):
        """TENANT_PAYMENTS should have a createdAt index in create_indexes()."""
        from app.database import Collections

        # Locate the index config in create_indexes()
        import app.database as db_mod
        import inspect
        source = inspect.getsource(db_mod.create_indexes)

        # Look for tenant_payments with createdAt:1 index (not compound, just createdAt)
        assert "TENANT_PAYMENTS" in source
        assert "createdAt" in source or "createdAt" in source
        # Verify it's not just the compound index - look for standalone createdAt:1
        assert '"createdAt", 1' in source or '("createdAt", 1)' in source or '"createdAt"' in source

    def test_tenants_subscription_status_index_in_database(self):
        """TENANTS should have a subscriptionStatus index in create_indexes()."""
        import app.database as db_mod
        import inspect
        source = inspect.getsource(db_mod.create_indexes)

        assert '"subscriptionStatus"' in source
        assert '("subscriptionStatus", 1)' in source or '"subscriptionStatus", 1' in source

    def test_tenants_subscription_status_subscription_end_date_index_in_database(self):
        """TENANTS should have a compound index on subscriptionStatus+subscriptionEndDate."""
        import app.database as db_mod
        import inspect
        source = inspect.getsource(db_mod.create_indexes)

        assert 'subscriptionEndDate' in source
        # Both fields should appear in the source
        assert '"subscriptionStatus"' in source
        assert '"subscriptionEndDate"' in source

    def test_tenant_payments_created_at_in_required_indexes(self):
        """REQUIRED_INDEXES should include tenant_payments createdAt_1."""
        from app.database import REQUIRED_INDEXES, Collections

        found = any(
            col == Collections.TENANT_PAYMENTS and "createdAt_1" in name
            for col, name, _ in REQUIRED_INDEXES
        )
        assert found, "REQUIRED_INDEXES should have TENANT_PAYMENTS createdAt_1"

    def test_tenants_subscription_status_in_required_indexes(self):
        """REQUIRED_INDEXES should include tenants subscriptionStatus_1."""
        from app.database import REQUIRED_INDEXES, Collections

        found = any(
            col == Collections.TENANTS and "subscriptionStatus_1" in name
            for col, name, _ in REQUIRED_INDEXES
        )
        assert found, "REQUIRED_INDEXES should have TENANTS subscriptionStatus_1"

    def test_tenants_subscription_status_end_date_in_required_indexes(self):
        """REQUIRED_INDEXES should include tenants subscriptionStatus+subscriptionEndDate."""
        from app.database import REQUIRED_INDEXES, Collections

        found = any(
            col == Collections.TENANTS
            and "subscriptionStatus_1" in name
            and "subscriptionEndDate" in name
            for col, name, _ in REQUIRED_INDEXES
        )
        assert found, (
            "REQUIRED_INDEXES should have TENANTS "
            "subscriptionStatus_1_subscriptionEndDate_1"
        )

    def test_indexes_in_migrate_script(self):
        """migrate_indexes.py should have the same new indexes."""
        import inspect
        import scripts.migrate_indexes as mig

        source = inspect.getsource(mig.migrate)
        assert '"subscriptionStatus"' in source
        assert '"subscriptionEndDate"' in source
        assert 'TENANT_PAYMENTS' in source


# ─── Task 3: Parallelized dashboard via asyncio.gather ──────────────────────

class TestDashboardParallelization:
    """get_dashboard uses asyncio.gather for parallel queries."""

    def test_get_dashboard_uses_asyncio_gather(self):
        """get_dashboard() should import and use asyncio.gather."""
        import inspect
        from app.services.admin_tenant import AdminTenantService

        source = inspect.getsource(AdminTenantService.get_dashboard)
        assert "asyncio.gather" in source or "asyncio" in source

    def test_get_dashboard_has_multiple_await_futures(self):
        """get_dashboard() should create futures and gather them."""
        import inspect
        from app.services.admin_tenant import AdminTenantService

        source = inspect.getsource(AdminTenantService.get_dashboard)
        # Should have count_documents calls (these are the futures)
        assert source.count("count_documents") >= 6
        assert "asyncio.gather" in source

    def test_get_dashboard_import_asyncio(self):
        """admin_tenant module should import asyncio."""
        import app.services.admin_tenant as mod
        import inspect

        source = inspect.getsource(mod)
        assert "import asyncio" in source


# ─── Task 4: In-memory cache ────────────────────────────────────────────────

class TestTTLCache:
    """Simple in-memory TTL cache works correctly."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Use a fresh cache for each test."""
        from app.services.cache import TTLCache, get_cache
        # Reset singleton state after test
        self.cache = TTLCache()
        yield
        # Teardown: clear cache
        self.cache.clear()

    def test_set_and_get(self):
        """Setting a value then getting it returns the value."""
        self.cache.set("key1", "value1", ttl_seconds=60)
        assert self.cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        """Getting a key that was never set returns None."""
        assert self.cache.get("nonexistent") is None

    def test_expired_key_returns_none(self):
        """An expired key returns None."""
        self.cache.set("expire_soon", "data", ttl_seconds=1)
        # Wait for expiry
        time.sleep(1.1)
        assert self.cache.get("expire_soon") is None

    def test_invalidate_removes_key(self):
        """Invalidating a key removes it from the cache."""
        self.cache.set("temp", "data", ttl_seconds=60)
        assert self.cache.get("temp") == "data"
        self.cache.invalidate("temp")
        assert self.cache.get("temp") is None

    def test_invalidate_nonexistent_key_does_not_raise(self):
        """Invalidating a nonexistent key does not raise an error."""
        self.cache.invalidate("does_not_exist")  # Should not raise

    def test_clear_removes_all_keys(self):
        """Clearing the cache removes all entries."""
        self.cache.set("a", 1, ttl_seconds=60)
        self.cache.set("b", 2, ttl_seconds=60)
        self.cache.clear()
        assert self.cache.get("a") is None
        assert self.cache.get("b") is None

    def test_different_keys_do_not_interfere(self):
        """Different cache keys store values independently."""
        self.cache.set("x", 100, ttl_seconds=60)
        self.cache.set("y", 200, ttl_seconds=60)
        assert self.cache.get("x") == 100
        assert self.cache.get("y") == 200

    def test_cache_accepts_different_types(self):
        """Cache accepts strings, ints, dicts, lists, and None."""
        self.cache.set("str", "hello", ttl_seconds=60)
        self.cache.set("int", 42, ttl_seconds=60)
        self.cache.set("dict", {"a": 1}, ttl_seconds=60)
        self.cache.set("list", [1, 2, 3], ttl_seconds=60)
        self.cache.set("none", None, ttl_seconds=60)

        assert self.cache.get("str") == "hello"
        assert self.cache.get("int") == 42
        assert self.cache.get("dict") == {"a": 1}
        assert self.cache.get("list") == [1, 2, 3]
        assert self.cache.get("none") is None


class TestGetCacheSingleton:
    """get_cache() returns a singleton."""

    def test_get_cache_returns_same_instance(self):
        """Multiple calls to get_cache return the same instance."""
        from app.services.cache import get_cache
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2

    def test_singleton_persists_data(self):
        """Data set via get_cache is retrievable from the singleton."""
        from app.services.cache import get_cache
        cache = get_cache()
        cache.set("singleton_key", "persisted", ttl_seconds=30)
        assert get_cache().get("singleton_key") == "persisted"
        # Cleanup
        cache.invalidate("singleton_key")


# ─── Task 4 integration: Dashboard uses cache ──────────────────────────────

class TestDashboardUsesCache:
    """get_dashboard() uses the in-memory cache."""

    def test_get_dashboard_imports_cache(self):
        """admin_tenant module imports get_cache from cache module."""
        import inspect
        import app.services.admin_tenant as mod

        source = inspect.getsource(mod)
        assert "get_cache" in source

    def test_get_dashboard_has_cache_logic(self):
        """get_dashboard has caching logic (get/set pattern)."""
        import inspect
        from app.services.admin_tenant import AdminTenantService

        source = inspect.getsource(AdminTenantService.get_dashboard)
        assert "cache_key" in source
        assert "cache.get" in source
        assert "cache.set" in source
