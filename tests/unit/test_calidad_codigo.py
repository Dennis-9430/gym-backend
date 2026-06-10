"""Tests for the calidad-codigo refactor: unified get_tenant_from_request.

Verifies:
1. The unified get_tenant_from_request exists in app.api.dependencies
2. All 7 routers no longer define their own get_tenant_from_header_* function
3. All 7 routers import and use get_tenant_from_request from deps
4. The old function is removed from app.services.tenant_auth
"""
import importlib
import inspect
import pytest

ROUTERS = [
    "clients",
    "employees",
    "invoices",
    "products",
    "reports",
    "sales",
    "tenants",
]

# ── RED: Unified dependency exists ─────────────────────────────────────────


class TestUnifiedDependencyExists:
    """RED: The unified get_tenant_from_request must be importable and callable."""

    def test_get_tenant_from_request_is_exported(self):
        """Unified dependency should be importable from app.api.dependencies."""
        from app.api.dependencies import get_tenant_from_request
        assert callable(get_tenant_from_request)

    def test_get_tenant_from_request_is_async(self):
        """Unified dependency should be a coroutine function."""
        from app.api.dependencies import get_tenant_from_request
        assert inspect.iscoroutinefunction(get_tenant_from_request)


# ── RED: Routers no longer define own deps ────────────────────────────────


class TestRoutersNoLongerDefineOwnDep:
    """RED: Each router must remove its duplicated get_tenant_from_header_*."""

    @pytest.mark.parametrize("router_name", ROUTERS)
    def test_router_does_not_define_get_tenant_from_header(self, router_name):
        """Router should NOT define its own get_tenant_from_header function."""
        module = importlib.import_module(f"app.routers.{router_name}")
        source = inspect.getsource(module)

        assert "async def get_tenant_from_header" not in source, (
            f"{router_name}.py still defines its own get_tenant_from_header_* function"
        )

    @pytest.mark.parametrize("router_name", ROUTERS)
    def test_router_imports_get_tenant_from_request(self, router_name):
        """Router should import get_tenant_from_request from dependencies."""
        module = importlib.import_module(f"app.routers.{router_name}")
        source = inspect.getsource(module)

        assert "get_tenant_from_request" in source, (
            f"{router_name}.py does not reference get_tenant_from_request"
        )

    @pytest.mark.parametrize("router_name", ROUTERS)
    def test_depends_uses_get_tenant_from_request(self, router_name):
        """Router should use Depends(get_tenant_from_request)."""
        module = importlib.import_module(f"app.routers.{router_name}")
        source = inspect.getsource(module)

        assert "Depends(get_tenant_from_request)" in source, (
            f"{router_name}.py does not use Depends(get_tenant_from_request)"
        )


# ── RED: tenant_auth.py no longer defines the function ────────────────────


class TestTenantAuthNoLongerDefinesDep:
    """RED: app.services.tenant_auth should not define get_tenant_from_header_tenants."""

    def test_tenant_auth_removes_get_tenant_from_header_tenants(self):
        """tenant_auth.py should remove the duplicated dependency function."""
        from app.services import tenant_auth
        source = inspect.getsource(tenant_auth)

        assert "async def get_tenant_from_header_tenants" not in source, (
            "tenant_auth.py still defines get_tenant_from_header_tenants"
        )


# ── RED: Router type annotations use dict not TenantResponse/TenantInfo ────


class TestRouterTypeAnnotations:
    """RED: Router type annotations should be dict, not TenantResponse/TenantInfo."""

    @pytest.mark.parametrize("router_name", ROUTERS)
    def test_router_uses_dict_for_tenant_param(self, router_name):
        """Router should use dict type annotation for tenant parameter."""
        module = importlib.import_module(f"app.routers.{router_name}")
        source = inspect.getsource(module)

        # The tenant parameter type should be dict (not TenantResponse or TenantInfo)
        # Find all Depends(get_tenant_from_request) and check their type hint
        # Look for patterns like "tenant: dict = Depends(get_tenant_from_request)"
        lines = source.split("\n")
        for i, line in enumerate(lines):
            if "Depends(get_tenant_from_request)" in line:
                assert "dict" in line, (
                    f"{router_name}.py line {i+1}: expected 'dict' type annotation, got: {line.strip()}"
                )
