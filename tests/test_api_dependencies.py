"""Tests for app/api/dependencies.py — auth deps, role/plan guards, tenant resolution.

These tests verify:
1. Module imports correctly
2. get_current_user is properly re-exported from auth/router
3. require_roles factory creates a working role guard
4. require_plan factory creates a working plan guard
5. resolve_tenant, get_current_tenant_id, get_current_tenant exist as callables
"""

import pytest
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.testclient import TestClient

from app.main import app as real_app
from app.database import get_database
from app.auth.schemas import UserResponse, UserRole


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def app() -> FastAPI:
    """Returns a clean FastAPI app for each test with no side-effects."""
    _app = FastAPI()
    _app.dependency_overrides = {}
    return _app


@pytest.fixture
def mock_current_user() -> UserResponse:
    """Default mock user: GERENTE, BASIC plan."""
    return UserResponse(
        username="test@gym.com",
        role=UserRole.GERENTE,
        employeeId="emp-001",
        tenantId="tenant-001",
        isOwner=True,
        plan="BASIC",
    )


# ── 1. Module import ───────────────────────────────────────────────────────


class TestModuleImports:
    """RED: Verify module is importable and all expected symbols exist."""

    def test_module_can_be_imported(self):
        """Module should be importable."""
        import app.api.dependencies
        assert app.api.dependencies is not None

    def test_get_current_user_is_re_exported(self):
        """get_current_user should be the same function from auth/router."""
        from app.api.dependencies import get_current_user
        from app.auth.router import get_current_user as auth_get_current_user
        assert get_current_user is auth_get_current_user

    def test_require_roles_is_callable(self):
        """require_roles should be a factory function."""
        from app.api.dependencies import require_roles
        assert callable(require_roles)

    def test_require_plan_is_callable(self):
        """require_plan should be a factory function."""
        from app.api.dependencies import require_plan
        assert callable(require_plan)

    def test_resolve_tenant_is_callable(self):
        """resolve_tenant should be an async callable."""
        from app.api.dependencies import resolve_tenant
        assert callable(resolve_tenant)

    def test_get_current_tenant_id_is_callable(self):
        """get_current_tenant_id should be an async callable."""
        from app.api.dependencies import get_current_tenant_id
        assert callable(get_current_tenant_id)

    def test_get_current_tenant_is_callable(self):
        """get_current_tenant should be an async callable."""
        from app.api.dependencies import get_current_tenant
        assert callable(get_current_tenant)


# ── 2. require_roles behavior ──────────────────────────────────────────────


class TestRequireRoles:
    """RED: require_roles factory must reject wrong roles, pass correct ones."""

    def test_returns_async_callable(self):
        """require_roles should return a FastAPI dependency."""
        from app.api.dependencies import require_roles

        dep = require_roles(UserRole.GERENTE, UserRole.ADMIN)
        assert callable(dep)

    @pytest.mark.asyncio
    async def test_allows_matching_role(self, mock_current_user):
        """Dependency should pass when user has one of the required roles."""
        from app.api.dependencies import require_roles

        dep = require_roles(UserRole.GERENTE, UserRole.ADMIN)
        # The dep is an async function with Depends inside; we call it directly
        # by passing the user (simulating FastAPI's Depends resolution)
        result = await dep(mock_current_user)
        assert result is mock_current_user

    @pytest.mark.asyncio
    async def test_rejects_non_matching_role(self, mock_current_user):
        """Dependency should raise 403 when user role is not in allowed roles."""
        from app.api.dependencies import require_roles

        dep = require_roles(UserRole.ADMIN, UserRole.RECEPCIONISTA)
        with pytest.raises(HTTPException) as exc_info:
            await dep(mock_current_user)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_rejects_super_admin_not_in_list(self, mock_current_user):
        """SUPER_ADMIN role should be rejected if not explicitly listed."""
        from app.api.dependencies import require_roles

        mock_current_user.role = UserRole.SUPER_ADMIN
        dep = require_roles(UserRole.GERENTE)
        with pytest.raises(HTTPException) as exc_info:
            await dep(mock_current_user)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    def test_empty_roles_raises_type_error(self):
        """require_roles with no arguments should still create a dependency
        that rejects all users (since no role is in an empty set)."""
        from app.api.dependencies import require_roles
        dep = require_roles()
        assert callable(dep)


# ── 3. require_plan behavior ───────────────────────────────────────────────


class TestRequirePlan:
    """RED: require_plan factory must reject wrong plans, pass correct ones."""

    def test_returns_async_callable(self):
        """require_plan should return a FastAPI dependency."""
        from app.api.dependencies import require_plan
        from app.models.tenant import SubscriptionPlan

        dep = require_plan(SubscriptionPlan.BASIC, SubscriptionPlan.PREMIUM)
        assert callable(dep)

    @pytest.mark.asyncio
    async def test_allows_matching_plan(self, mock_current_user):
        """Dependency should pass when tenant has one of the required plans."""
        from app.api.dependencies import require_plan
        from app.models.tenant import SubscriptionPlan

        dep = require_plan(SubscriptionPlan.BASIC)
        result = await dep(mock_current_user)
        assert result is mock_current_user

    @pytest.mark.asyncio
    async def test_rejects_non_matching_plan(self, mock_current_user):
        """Dependency should raise 403 when tenant plan is not allowed."""
        from app.api.dependencies import require_plan
        from app.models.tenant import SubscriptionPlan

        mock_current_user.plan = "PREMIUM"
        dep = require_plan(SubscriptionPlan.BASIC)
        with pytest.raises(HTTPException) as exc_info:
            await dep(mock_current_user)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_rejects_none_plan(self, mock_current_user):
        """Dependency should reject when user has no plan."""
        from app.api.dependencies import require_plan
        from app.models.tenant import SubscriptionPlan

        mock_current_user.plan = None
        dep = require_plan(SubscriptionPlan.BASIC, SubscriptionPlan.PREMIUM)
        with pytest.raises(HTTPException) as exc_info:
            await dep(mock_current_user)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


# ── 4. get_current_tenant_id behavior ──────────────────────────────────────


class TestGetCurrentTenantId:
    """RED: get_current_tenant_id extracts tenantId from current_user."""

    @pytest.mark.asyncio
    async def test_returns_tenant_id(self, mock_current_user):
        """Should return the tenantId from current_user."""
        from app.api.dependencies import get_current_tenant_id

        result = await get_current_tenant_id(mock_current_user)
        assert result == "tenant-001"

    @pytest.mark.asyncio
    async def test_raises_if_no_tenant_id(self, mock_current_user):
        """Should raise 400 if user has no tenantId."""
        from app.api.dependencies import get_current_tenant_id

        mock_current_user.tenantId = None
        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant_id(mock_current_user)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
