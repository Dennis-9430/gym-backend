"""Tests for PR #2: Transaction manager + atomicity.

Verifies that:
1. TransactionManager works correctly with transactions enabled
2. TransactionManager fallback mode (no session)
3. Compensation runs on error in fallback mode
4. Compensation reversal order
5. Service methods accept optional session parameter
6. Backward compatibility (methods work without session)
"""
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClientSession


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_async_session(**kwargs):
    """Create a mock session with async methods properly configured.

    AsyncMock(spec=...) doesn't make attribute access return AsyncMock,
    so we must explicitly set the async methods.
    """
    session = MagicMock(spec=AsyncIOMotorClientSession, **kwargs)
    session.commit_transaction = AsyncMock()
    session.abort_transaction = AsyncMock()
    session.end_session = AsyncMock()
    # start_transaction is not async in Motor — keep as regular Mock
    return session


def _make_db_with_client(client=None):
    """Create a mock database with an optional mock client."""
    db = MagicMock(spec=AsyncIOMotorDatabase)
    db.client = client or MagicMock()
    return db


def _make_collection(return_values=None):
    """Create a mock collection with async methods.

    Args:
        return_values: Optional dict of method_name -> return_value.
            If value is a list, it's set as side_effect (sequential responses).
            Otherwise set as return_value.
    """
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock()
    col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))

    if return_values:
        for method, value in return_values.items():
            if isinstance(value, list):
                getattr(col, method).side_effect = value
            else:
                getattr(col, method).return_value = value

    return col


# ══════════════════════════════════════════════════════════════════════════════
# Module imports
# ══════════════════════════════════════════════════════════════════════════════


class TestModuleImports:
    """Verify the module is importable and exposes expected names."""

    def test_module_can_be_imported(self):
        """Module should be importable."""
        import app.services.db_utils
        assert app.services.db_utils is not None

    def test_transaction_manager_class_exists(self):
        """TransactionManager class should be exposed."""
        from app.services.db_utils import TransactionManager
        assert TransactionManager is not None

    def test_transaction_manager_has_expected_methods(self):
        """TransactionManager should have the expected methods."""
        from app.services.db_utils import TransactionManager
        assert hasattr(TransactionManager, '__aenter__')
        assert hasattr(TransactionManager, '__aexit__')
        assert hasattr(TransactionManager, 'add_compensation')


# ══════════════════════════════════════════════════════════════════════════════
# TransactionManager — enabled mode
# ══════════════════════════════════════════════════════════════════════════════


class TestTransactionManagerEnabled:
    """RED: TransactionManager with transactions enabled."""

    @pytest.mark.asyncio
    async def test_creates_session_and_starts_transaction(self):
        """When enabled, __aenter__ should start a session and transaction."""
        from app.services.db_utils import TransactionManager

        mock_session = _make_async_session()
        mock_client = AsyncMock()
        mock_client.start_session = AsyncMock(return_value=mock_session)

        mock_db = _make_db_with_client(mock_client)

        tx = TransactionManager(mock_db, enabled=True)
        session = await tx.__aenter__()

        assert session is mock_session
        mock_client.start_session.assert_awaited_once()
        mock_session.start_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_commits_on_success(self):
        """When no exception occurs, __aexit__ should commit and end session."""
        from app.services.db_utils import TransactionManager

        mock_session = _make_async_session()
        mock_client = AsyncMock()
        mock_client.start_session = AsyncMock(return_value=mock_session)
        mock_db = _make_db_with_client(mock_client)

        tx = TransactionManager(mock_db, enabled=True)
        tx.session = mock_session

        await tx.__aexit__(None, None, None)

        mock_session.commit_transaction.assert_awaited_once()
        mock_session.abort_transaction.assert_not_called()
        mock_session.end_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aborts_on_exception(self):
        """When exception occurs, __aexit__ should abort and end session."""
        from app.services.db_utils import TransactionManager

        mock_session = _make_async_session()
        mock_client = AsyncMock()
        mock_client.start_session = AsyncMock(return_value=mock_session)
        mock_db = _make_db_with_client(mock_client)

        tx = TransactionManager(mock_db, enabled=True)
        tx.session = mock_session

        await tx.__aexit__(ValueError, ValueError("test"), None)

        mock_session.abort_transaction.assert_awaited_once()
        mock_session.commit_transaction.assert_not_called()
        mock_session.end_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_end_session_called_even_if_commit_fails(self):
        """end_session should be called even if commit_transaction raises."""
        from app.services.db_utils import TransactionManager

        mock_session = _make_async_session()
        mock_session.commit_transaction = AsyncMock(
            side_effect=RuntimeError("commit failed")
        )
        mock_client = AsyncMock()
        mock_client.start_session = AsyncMock(return_value=mock_session)
        mock_db = _make_db_with_client(mock_client)

        tx = TransactionManager(mock_db, enabled=True)
        tx.session = mock_session

        with pytest.raises(RuntimeError, match="commit failed"):
            await tx.__aexit__(None, None, None)

        mock_session.commit_transaction.assert_awaited_once()
        mock_session.end_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aborts_and_ends_on_exception_even_with_inner_try(self):
        """abort + end_session both called when exception occurs in body."""
        from app.services.db_utils import TransactionManager

        mock_session = _make_async_session()
        mock_client = AsyncMock()
        mock_client.start_session = AsyncMock(return_value=mock_session)
        mock_db = _make_db_with_client(mock_client)

        tx = TransactionManager(mock_db, enabled=True)
        with pytest.raises(ValueError, match="ops"):
            async with tx as session:
                assert session is mock_session
                raise ValueError("ops")

        mock_session.start_transaction.assert_called_once()
        mock_session.abort_transaction.assert_awaited_once()
        mock_session.commit_transaction.assert_not_called()
        mock_session.end_session.assert_awaited_once()


# ══════════════════════════════════════════════════════════════════════════════
# TransactionManager — fallback mode
# ══════════════════════════════════════════════════════════════════════════════


class TestTransactionManagerFallback:
    """GREEN: TransactionManager fallback mode (no session returned)."""

    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self):
        """When disabled, __aenter__ should return None."""
        from app.services.db_utils import TransactionManager

        mock_db = _make_db_with_client()

        tx = TransactionManager(mock_db, enabled=False)
        session = await tx.__aenter__()

        assert session is None

    @pytest.mark.asyncio
    async def test_noop_on_success_in_fallback(self):
        """When disabled and no exception, __aexit__ should do nothing."""
        from app.services.db_utils import TransactionManager

        mock_db = _make_db_with_client()

        tx = TransactionManager(mock_db, enabled=False)
        # No session, no compensation registered
        await tx.__aexit__(None, None, None)
        # Should not raise

    @pytest.mark.asyncio
    async def test_runs_compensation_on_error_in_fallback(self):
        """When disabled and exception occurs, compensation should run."""
        from app.services.db_utils import TransactionManager

        mock_db = _make_db_with_client()
        compensation_fn = AsyncMock()

        tx = TransactionManager(mock_db, enabled=False)
        tx.add_compensation("undo something", compensation_fn, "arg1", key="val1")

        await tx.__aexit__(ValueError, ValueError("test"), None)

        compensation_fn.assert_awaited_once_with("arg1", key="val1")

    @pytest.mark.asyncio
    async def test_no_compensation_on_success_in_fallback(self):
        """When disabled and no exception, compensation should NOT run."""
        from app.services.db_utils import TransactionManager

        mock_db = _make_db_with_client()
        compensation_fn = AsyncMock()

        tx = TransactionManager(mock_db, enabled=False)
        tx.add_compensation("undo something", compensation_fn)

        await tx.__aexit__(None, None, None)

        compensation_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_compensation_reversal_order(self):
        """Compensation steps should run in reverse order."""
        from app.services.db_utils import TransactionManager

        mock_db = _make_db_with_client()
        order = []

        async def comp_a():
            order.append("a")

        async def comp_b():
            order.append("b")

        async def comp_c():
            order.append("c")

        tx = TransactionManager(mock_db, enabled=False)
        tx.add_compensation("a", comp_a)
        tx.add_compensation("b", comp_b)
        tx.add_compensation("c", comp_c)

        await tx.__aexit__(ValueError, ValueError("test"), None)

        assert order == ["c", "b", "a"], (
            f"Expected reverse order ['c', 'b', 'a'], got {order}"
        )

    @pytest.mark.asyncio
    async def test_compensation_continues_after_failure(self):
        """If one compensation step fails, remaining steps should still run."""
        from app.services.db_utils import TransactionManager

        mock_db = _make_db_with_client()
        order = []

        async def comp_a():
            order.append("a")

        async def comp_b():
            order.append("b")
            raise RuntimeError("comp_b failed")

        async def comp_c():
            order.append("c")

        tx = TransactionManager(mock_db, enabled=False)
        tx.add_compensation("a", comp_a)
        tx.add_compensation("b", comp_b)
        tx.add_compensation("c", comp_c)

        # Should not raise — failures are logged, not propagated
        await tx.__aexit__(ValueError, ValueError("test"), None)

        assert order == ["c", "b", "a"], (
            f"All compensations should run even if one fails, got {order}"
        )

    @pytest.mark.asyncio
    async def test_no_session_started_when_disabled(self):
        """When disabled, no session methods should be called."""
        from app.services.db_utils import TransactionManager

        mock_client = MagicMock()
        mock_db = _make_db_with_client(mock_client)

        tx = TransactionManager(mock_db, enabled=False)
        async with tx as session:
            assert session is None

        mock_client.start_session.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# TransactionManager — ctx manager integration
# ══════════════════════════════════════════════════════════════════════════════


class TestTransactionManagerContextManager:
    """REFACTOR: TransactionManager used as async context manager."""

    @pytest.mark.asyncio
    async def test_async_with_returns_session_when_enabled(self):
        """async with should return session when enabled."""
        from app.services.db_utils import TransactionManager

        mock_session = _make_async_session()
        mock_client = AsyncMock()
        mock_client.start_session = AsyncMock(return_value=mock_session)
        mock_db = _make_db_with_client(mock_client)

        tx = TransactionManager(mock_db, enabled=True)
        async with tx as session:
            assert session is mock_session

        mock_session.commit_transaction.assert_awaited_once()
        mock_session.end_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_with_returns_none_when_disabled(self):
        """async with should return None when disabled."""
        from app.services.db_utils import TransactionManager

        mock_db = _make_db_with_client()

        tx = TransactionManager(mock_db, enabled=False)
        async with tx as session:
            assert session is None

    @pytest.mark.asyncio
    async def test_async_with_aborts_on_exception_when_enabled(self):
        """async with should abort on exception when enabled."""
        from app.services.db_utils import TransactionManager

        mock_session = _make_async_session()
        mock_client = AsyncMock()
        mock_client.start_session = AsyncMock(return_value=mock_session)
        mock_db = _make_db_with_client(mock_client)

        tx = TransactionManager(mock_db, enabled=True)
        with pytest.raises(ValueError, match="test error"):
            async with tx as session:
                assert session is mock_session
                raise ValueError("test error")

        mock_session.abort_transaction.assert_awaited_once()
        mock_session.end_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_with_runs_compensation_on_error_when_disabled(self):
        """async with should run compensation on error when disabled."""
        from app.services.db_utils import TransactionManager

        mock_db = _make_db_with_client()
        compensation_fn = AsyncMock()

        tx = TransactionManager(mock_db, enabled=False)
        tx.add_compensation("undo", compensation_fn, "arg")

        with pytest.raises(ValueError, match="test"):
            async with tx as _:
                raise ValueError("test")

        compensation_fn.assert_awaited_once_with("arg")


# ══════════════════════════════════════════════════════════════════════════════
# Service methods — session parameter (tenants)
# ══════════════════════════════════════════════════════════════════════════════


class TestTenantAuthServiceSession:
    """RED: register() should accept optional session parameter."""

    def test_register_accepts_session_parameter(self):
        """register() should accept an optional session parameter."""
        from app.services.tenant_auth import TenantAuthService
        import inspect
        sig = inspect.signature(TenantAuthService.register)
        assert 'session' in sig.parameters, (
            "register() should have a 'session' parameter"
        )
        param = sig.parameters['session']
        assert param.default is None, (
            "session should default to None for backward compatibility"
        )

    @pytest.mark.asyncio
    async def test_register_passes_session_to_inserts(self):
        """register() should pass session to db insert operations."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import TenantCreate, SubscriptionPlan

        mock_session = MagicMock(spec=AsyncIOMotorClientSession)
        mock_collection = _make_collection()

        # Mock db so that self.db.tenants, self.db.employees, etc. return
        # the same mock collection
        mock_db = MagicMock(spec=AsyncIOMotorDatabase)
        mock_db.tenants = mock_collection
        mock_db.employees = mock_collection
        mock_db.users = mock_collection
        mock_db.services = mock_collection
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        service = TenantAuthService(mock_db)
        data = TenantCreate(
            email="test@example.com",
            businessName="Test Gym",
            businessPhone="123456789",
            ownerFirstName="Test",
            ownerLastName="Owner",
            password="password123",
            plan=SubscriptionPlan.BASIC,
            paymentMethod="CARD",
            paymentMonths=1,
        )

        utcnow = datetime(2025, 1, 1)
        with patch('app.services.tenant_auth.uuid4', return_value="test-uuid-123"):
            with patch('app.services.tenant_auth.get_password_hash', return_value="hashed"):
                with patch('app.services.tenant_auth.datetime') as mock_dt:
                    mock_dt.utcnow = MagicMock(return_value=utcnow)
                    mock_dt.timedelta = timedelta
                    await service.register(data, session=mock_session)

        # Verify session was passed to at least the key insert operations
        insert_calls = mock_collection.insert_one.call_args_list
        assert len(insert_calls) > 0, "Expected at least one insert_one call"
        for call_args in insert_calls:
            _, kwargs = call_args
            assert 'session' in kwargs, (
                f"insert_one should receive session kwarg, got {kwargs}"
            )
            assert kwargs['session'] is mock_session

        # Also verify update_one received session
        update_calls = mock_collection.update_one.call_args_list
        assert len(update_calls) > 0, "Expected at least one update_one call"
        for call_args in update_calls:
            _, kwargs = call_args
            assert 'session' in kwargs, (
                f"update_one should receive session kwarg, got {kwargs}"
            )
            assert kwargs['session'] is mock_session


# ══════════════════════════════════════════════════════════════════════════════
# Service methods — session parameter (admin)
# ══════════════════════════════════════════════════════════════════════════════


class TestAdminTenantServiceSession:
    """GREEN: delete_tenant() should accept optional session parameter."""

    def test_delete_tenant_accepts_session_parameter(self):
        """delete_tenant() should accept an optional session parameter."""
        from app.services.admin_tenant import AdminTenantService
        import inspect
        sig = inspect.signature(AdminTenantService.delete_tenant)
        assert 'session' in sig.parameters, (
            "delete_tenant() should have a 'session' parameter"
        )
        param = sig.parameters['session']
        assert param.default is None, (
            "session should default to None for backward compatibility"
        )

    @pytest.mark.asyncio
    async def test_delete_tenant_passes_session_to_deletes(self):
        """delete_tenant() should pass session to delete operations."""
        from app.services.admin_tenant import AdminTenantService

        mock_session = MagicMock(spec=AsyncIOMotorClientSession)
        mock_collection = _make_collection(
            return_values={
                "find_one": {"tenantId": "test-id", "businessName": "Test"},
            }
        )

        mock_db = MagicMock(spec=AsyncIOMotorDatabase)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        service = AdminTenantService(mock_db)
        await service.delete_tenant("test-id", session=mock_session)

        # Verify session was passed to delete_many calls
        delete_many_calls = mock_collection.delete_many.call_args_list
        assert len(delete_many_calls) > 0, "Expected at least one delete_many call"
        for call_args in delete_many_calls:
            _, kwargs = call_args
            assert 'session' in kwargs, (
                f"delete_many should receive session kwarg, got {kwargs}"
            )
            assert kwargs['session'] is mock_session

        # Verify session was passed to delete_one
        delete_one_calls = mock_collection.delete_one.call_args_list
        assert len(delete_one_calls) > 0, "Expected at least one delete_one call"
        for call_args in delete_one_calls:
            _, kwargs = call_args
            assert 'session' in kwargs, (
                f"delete_one should receive session kwarg, got {kwargs}"
            )
            assert kwargs['session'] is mock_session


class TestAdminPaymentServiceSession:
    """GREEN: approve_payment() should accept optional session parameter."""

    def test_approve_payment_accepts_session_parameter(self):
        """approve_payment() should accept an optional session parameter."""
        from app.services.admin_payment import AdminPaymentService
        import inspect
        sig = inspect.signature(AdminPaymentService.approve_payment)
        assert 'session' in sig.parameters, (
            "approve_payment() should have a 'session' parameter"
        )
        param = sig.parameters['session']
        assert param.default is None, (
            "session should default to None for backward compatibility"
        )

    @pytest.mark.asyncio
    async def test_approve_payment_passes_session_to_updates(self):
        """approve_payment() should pass session to update operations."""
        from app.services.admin_payment import AdminPaymentService

        mock_session = MagicMock(spec=AsyncIOMotorClientSession)
        mock_collection = _make_collection(
            return_values={
                "find_one": [
                    {"tenantId": "test-id", "businessName": "Test", "plan": "BASIC"},
                    {"_id": "payment-id", "tenantId": "test-id", "months": 1,
                     "plan": "BASIC", "amount": 20.0},
                ],
            }
        )

        mock_db = MagicMock(spec=AsyncIOMotorDatabase)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        service = AdminPaymentService(mock_db)
        with patch('app.services.admin_payment.datetime') as mock_dt:
            mock_dt.utcnow = MagicMock(return_value=datetime(2025, 1, 1))
            mock_dt.timedelta = timedelta
            await service.approve_payment(
                "test-id", "approved", "admin", session=mock_session
            )

        # Verify session was passed to update_one calls
        update_calls = mock_collection.update_one.call_args_list
        assert len(update_calls) > 0, "Expected at least one update_one call"
        for call_args in update_calls:
            _, kwargs = call_args
            assert 'session' in kwargs, (
                f"update_one should receive session kwarg, got {kwargs}"
            )
            assert kwargs['session'] is mock_session


# ══════════════════════════════════════════════════════════════════════════════
# Backward compatibility — methods work without session
# ══════════════════════════════════════════════════════════════════════════════


class TestBackwardCompatibility:
    """Backward compat: methods work without session (default)."""

    @pytest.mark.asyncio
    async def test_register_works_without_session(self):
        """register() should work when called without session (default)."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import TenantCreate, SubscriptionPlan

        mock_collection = _make_collection()
        mock_db = MagicMock(spec=AsyncIOMotorDatabase)
        mock_db.tenants = mock_collection
        mock_db.employees = mock_collection
        mock_db.users = mock_collection
        mock_db.services = mock_collection
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        service = TenantAuthService(mock_db)
        data = TenantCreate(
            email="test@example.com",
            businessName="Test Gym",
            businessPhone="123456789",
            ownerFirstName="Test",
            ownerLastName="Owner",
            password="password123",
            plan=SubscriptionPlan.BASIC,
            paymentMethod="CARD",
            paymentMonths=1,
        )

        utcnow = datetime(2025, 1, 1)
        with patch('app.services.tenant_auth.uuid4', return_value="test-uuid-123"):
            with patch('app.services.tenant_auth.get_password_hash', return_value="hashed"):
                with patch('app.services.tenant_auth.datetime') as mock_dt:
                    mock_dt.utcnow = MagicMock(return_value=utcnow)
                    mock_dt.timedelta = timedelta
                    # Call WITHOUT session — should work
                    result = await service.register(data)

        assert result is not None
        assert "tenantId" in result

    @pytest.mark.asyncio
    async def test_register_with_session_none(self):
        """register() should work when session=None is explicitly passed."""
        from app.services.tenant_auth import TenantAuthService
        from app.models.tenant import TenantCreate, SubscriptionPlan

        mock_collection = _make_collection()
        mock_db = MagicMock(spec=AsyncIOMotorDatabase)
        mock_db.tenants = mock_collection
        mock_db.employees = mock_collection
        mock_db.users = mock_collection
        mock_db.services = mock_collection
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        service = TenantAuthService(mock_db)
        data = TenantCreate(
            email="test@example.com",
            businessName="Test Gym",
            businessPhone="123456789",
            ownerFirstName="Test",
            ownerLastName="Owner",
            password="password123",
            plan=SubscriptionPlan.BASIC,
            paymentMethod="CARD",
            paymentMonths=1,
        )

        utcnow = datetime(2025, 1, 1)
        with patch('app.services.tenant_auth.uuid4', return_value="test-uuid-123"):
            with patch('app.services.tenant_auth.get_password_hash', return_value="hashed"):
                with patch('app.services.tenant_auth.datetime') as mock_dt:
                    mock_dt.utcnow = MagicMock(return_value=utcnow)
                    mock_dt.timedelta = timedelta
                    # Call with session=None explicitly — should work
                    result = await service.register(data, session=None)

        assert result is not None
        assert "tenantId" in result

    @pytest.mark.asyncio
    async def test_delete_tenant_works_without_session(self):
        """delete_tenant() should work without session (default)."""
        from app.services.admin_tenant import AdminTenantService

        mock_collection = _make_collection(
            return_values={
                "find_one": {"tenantId": "test-id", "businessName": "Test"},
            }
        )
        mock_db = MagicMock(spec=AsyncIOMotorDatabase)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        service = AdminTenantService(mock_db)
        result = await service.delete_tenant("test-id")

        assert result is not None
        assert "message" in result

    @pytest.mark.asyncio
    async def test_approve_payment_works_without_session(self):
        """approve_payment() should work without session (default)."""
        from app.services.admin_payment import AdminPaymentService

        mock_collection = _make_collection(
            return_values={
                "find_one": [
                    {"tenantId": "test-id", "businessName": "Test", "plan": "BASIC"},
                    {"_id": "payment-id", "tenantId": "test-id", "months": 1,
                     "plan": "BASIC", "amount": 20.0},
                ],
            }
        )
        mock_db = MagicMock(spec=AsyncIOMotorDatabase)
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        service = AdminPaymentService(mock_db)
        with patch('app.services.admin_payment.datetime') as mock_dt:
            mock_dt.utcnow = MagicMock(return_value=datetime(2025, 1, 1))
            mock_dt.timedelta = timedelta
            result = await service.approve_payment(
                "test-id", "approved", "admin"
            )

        assert result is not None
        assert "message" in result


# ══════════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════════


class TestMongoDBTransactionsEnabledConfig:
    """Verify MONGODB_TRANSACTIONS_ENABLED is in settings."""

    def test_config_has_transactions_enabled(self):
        """Settings should have MONGODB_TRANSACTIONS_ENABLED."""
        from app.config import settings
        assert hasattr(settings, 'MONGODB_TRANSACTIONS_ENABLED')

    def test_config_defaults_to_false(self):
        """MONGODB_TRANSACTIONS_ENABLED should default to False."""
        from app.config import settings
        assert settings.MONGODB_TRANSACTIONS_ENABLED is False

    def test_config_is_bool(self):
        """MONGODB_TRANSACTIONS_ENABLED should be a bool."""
        from app.config import settings
        assert isinstance(settings.MONGODB_TRANSACTIONS_ENABLED, bool)
