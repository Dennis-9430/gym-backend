"""Tests for PR #1: Replace .to_list(None) with explicit limits + add projections.

Verifies that:
1. All 9 .to_list(None) occurrences are replaced with integer limits
2. Admin find() queries use explicit field projections
"""
import inspect
import re
import pytest


# ── Source module paths ─────────────────────────────────────────────────────

AUDIT_SERVICE = "app.services.audit_service"
ADMIN_PAYMENT = "app.services.admin_payment"
ADMIN_TENANT = "app.services.admin_tenant"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_source_lines(module_path: str, class_name: str, method: str) -> list[str]:
    """Return source lines for a given method."""
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    method_obj = getattr(cls, method)
    lines, _ = inspect.getsourcelines(method_obj)
    return lines


def _get_source_text(module_path: str, class_name: str, method: str) -> str:
    """Return concatenated source text for a given method."""
    return "".join(_get_source_lines(module_path, class_name, method))


TO_LIST_NONE_RE = re.compile(r"\.to_list\(None\)")


# ══════════════════════════════════════════════════════════════════════════════
# RED: Tests that verify .to_list(None) is gone
# ══════════════════════════════════════════════════════════════════════════════

class TestToListLimitsAuditService:
    """Task 1.1 — audit_service.py query_logs: .to_list(None) → .to_list(limit)"""

    MODULE = AUDIT_SERVICE
    CLASS = "AuditService"
    METHOD = "query_logs"

    def test_query_logs_to_list_has_integer_limit(self):
        """query_logs .to_list() should use 'limit' parameter, not None."""
        source = _get_source_text(self.MODULE, self.CLASS, self.METHOD)
        # Must NOT contain .to_list(None)
        assert "to_list(None)" not in source, "query_logs still has .to_list(None)"
        # Must contain .to_list(limit)
        assert ".to_list(limit)" in source, (
            "query_logs should use .to_list(limit) where limit is the method parameter"
        )


class TestToListLimitsAdminPayment:
    """Tasks 1.2–1.3 — admin_payment.py list_payments, list_pending_payments"""

    MODULE = ADMIN_PAYMENT
    CLASS = "AdminPaymentService"

    def test_list_payments_to_list_has_limit_param(self):
        """list_payments .to_list() should use 'limit' parameter."""
        source = _get_source_text(self.MODULE, self.CLASS, "list_payments")
        assert "to_list(None)" not in source
        assert ".to_list(limit)" in source, (
            "list_payments should use .to_list(limit) where limit is the pagination param"
        )

    def test_list_pending_payments_to_list_has_limit_param(self):
        """list_pending_payments .to_list() should use 'limit' parameter."""
        source = _get_source_text(self.MODULE, self.CLASS, "list_pending_payments")
        assert "to_list(None)" not in source
        # The first cursor (tenant_payments) uses .to_list(limit)
        assert ".to_list(limit)" in source, (
            "list_pending_payments payments query should use .to_list(limit)"
        )

    def test_list_pending_payments_tenant_fetch_uses_len_ids(self):
        """list_pending_payments batch tenant fetch .to_list() should use len(tenant_ids)."""
        source = _get_source_text(self.MODULE, self.CLASS, "list_pending_payments")
        assert "to_list(None)" not in source
        # The tenant batch fetch uses .to_list(len(tenant_ids)) or similar
        has_len_ids = ".to_list(len(tenant_ids))" in source or ".to_list(len(tenantIds))" in source
        assert has_len_ids, (
            "list_pending_payments tenant batch fetch should use .to_list(len(tenant_ids))"
        )


class TestToListLimitsAdminTenant:
    """Tasks 1.4–1.8 — admin_tenant.py get_dashboard, list_tenants, get_tenant"""

    MODULE = ADMIN_TENANT
    CLASS = "AdminTenantService"

    def test_dashboard_revenue_to_list_5000(self):
        """get_dashboard monthly revenue aggregation .to_list() should use 5000."""
        source = _get_source_text(self.MODULE, self.CLASS, "get_dashboard")
        assert "to_list(None)" not in source
        assert ".to_list(5000)" in source, (
            "get_dashboard revenue aggregate should use .to_list(5000)"
        )

    def test_dashboard_recent_payments_to_list_10(self):
        """get_dashboard recent payments (already .limit(10)) .to_list() should use 10."""
        source = _get_source_text(self.MODULE, self.CLASS, "get_dashboard")
        # Should have .to_list(10) for the recent payments query
        recent_calls = [m for m in re.findall(r"\.to_list\(\d+\)", source) if "5000" not in m]
        assert any("10" in call for call in recent_calls), (
            "get_dashboard recent payments should use .to_list(10) — "
            "found: %s" % recent_calls
        )

    def test_dashboard_tenant_batch_fetch_to_list_10(self):
        """get_dashboard batch tenant fetch (behind .limit(10)) .to_list() should use 10."""
        source = _get_source_text(self.MODULE, self.CLASS, "get_dashboard")
        calls = re.findall(r"\.to_list\((\d+)\)", source)
        # There should be at least two .to_list(10) calls (recent payments + tenant fetch)
        assert calls.count("10") >= 2, (
            "get_dashboard should have at least 2 calls with .to_list(10)"
        )

    def test_list_tenants_to_list_uses_limit_param(self):
        """list_tenants .to_list() should use 'limit' parameter."""
        source = _get_source_text(self.MODULE, self.CLASS, "list_tenants")
        assert "to_list(None)" not in source
        assert ".to_list(limit)" in source, (
            "list_tenants should use .to_list(limit)"
        )

    def test_get_tenant_payment_summary_to_list_1(self):
        """get_tenant payment summary (single $group) .to_list() should use 1."""
        source = _get_source_text(self.MODULE, self.CLASS, "get_tenant")
        assert "to_list(None)" not in source
        # The payment summary $group returns at most 1 document
        assert ".to_list(1)" in source or ".to_list(limit)" in source, (
            "get_tenant payment summary should use .to_list(1)"
        )


# ══════════════════════════════════════════════════════════════════════════════
# RED: Tests that verify projections exist
# ══════════════════════════════════════════════════════════════════════════════

class TestProjectionsAdminTenant:
    """Tasks 2.1–2.2 — admin_tenant.py projections"""

    MODULE = ADMIN_TENANT
    CLASS = "AdminTenantService"

    def test_list_tenants_has_projection(self):
        """list_tenants .find() should include a projection dict."""
        source = _get_source_text(self.MODULE, self.CLASS, "list_tenants")
        assert "to_list(None)" not in source
        # find() should have a second argument (projection dict) or chained .project()
        # e.g., .find(query, {"field": 1, ...})
        find_calls = re.findall(r"\.find\([^)]+\)", source)
        has_projection = False
        for call in find_calls:
            if '"tenantId"' in call or '"businessName"' in call or '"plan"' in call:
                has_projection = True
                break
        assert has_projection, (
            "list_tenants find() should include a projection dict with tenant fields. "
            "Found find() calls: %s" % find_calls
        )

    def test_dashboard_payments_has_projection(self):
        """get_dashboard recent payments .find() should include a projection dict."""
        source = _get_source_text(self.MODULE, self.CLASS, "get_dashboard")
        # The batch tenant fetch already has projection — check payments query has one too
        find_calls = re.findall(r"\.find\([^)]*\{[^}]*\d[^}]*\}[^)]*\)", source)
        assert len(find_calls) >= 1, (
            "get_dashboard should have at least one find() call with field projection"
        )


class TestProjectionsAdminPayment:
    """Tasks 2.3–2.4 — admin_payment.py projections"""

    MODULE = ADMIN_PAYMENT
    CLASS = "AdminPaymentService"

    def test_list_payments_has_projection(self):
        """list_payments .find() should include a projection dict."""
        source = _get_source_text(self.MODULE, self.CLASS, "list_payments")
        # find(query) should include projection: .find(query, {"field": 1, ...})
        has_projection = '"tenantId"' in source and '"amount"' in source and '"status"' in source
        assert has_projection, (
            "list_payments find() should include a projection dict with payment fields"
        )

    def test_list_pending_payments_has_projection(self):
        """list_pending_payments .find() should include a projection dict."""
        source = _get_source_text(self.MODULE, self.CLASS, "list_pending_payments")
        has_projection = '"tenantId"' in source and '"amount"' in source and '"status"' in source
        assert has_projection, (
            "list_pending_payments find() should include a projection dict with payment fields"
        )

    def test_list_pending_payments_tenant_fetch_has_projection(self):
        """list_pending_payments batch tenant fetch already has projection — verify it's preserved."""
        source = _get_source_text(self.MODULE, self.CLASS, "list_pending_payments")
        # The batch tenant fetch already has {"tenantId": 1, "businessName": 1, ...}
        assert '"businessName"' in source and '"businessCode"' in source, (
            "list_pending_payments batch tenant fetch should preserve its projection"
        )
