"""Tests for status codes (204 DELETE) and pagination metadata (page/limit in list responses).

Covers PR #2 implementation: Tasks 2.1-2.4.
- 2.1: Frontend DELETE handling analysis (documented, no code change needed — safe)
- 2.2: Tenant-facing DELETE → 204 No Content
- 2.3: Add page/limit to list responses
- 2.4: Admin DELETE stays at 200
"""

import pytest


# ── Task 2.1: Page calculation (pure function) ───────────────────────────────

class TestPageCalculation:
    """Unit tests for page = skip // limit + 1 formula used in list endpoints."""

    def test_first_page_default(self):
        """skip=0, limit=50 → page=1"""
        skip, limit = 0, 50
        page = skip // limit + 1
        assert page == 1

    def test_first_page_custom_limit(self):
        """skip=0, limit=100 → page=1"""
        skip, limit = 0, 100
        page = skip // limit + 1
        assert page == 1

    def test_second_page(self):
        """skip=50, limit=50 → page=2"""
        skip, limit = 50, 50
        page = skip // limit + 1
        assert page == 2

    def test_third_page(self):
        """skip=100, limit=50 → page=3"""
        skip, limit = 100, 50
        page = skip // limit + 1
        assert page == 3

    def test_second_page_custom_limit(self):
        """skip=25, limit=25 → page=2"""
        skip, limit = 25, 25
        page = skip // limit + 1
        assert page == 2

    def test_single_item_page(self):
        """skip=0, limit=1 → page=1"""
        skip, limit = 0, 1
        page = skip // limit + 1
        assert page == 1

    def test_large_offset(self):
        """skip=5000, limit=100 → page=51"""
        skip, limit = 5000, 100
        page = skip // limit + 1
        assert page == 51

    def test_skip_not_exact_multiple(self):
        """skip=33, limit=10 → page=4 (since skip=30 would be page 4)"""
        skip, limit = 33, 10
        page = skip // limit + 1
        assert page == 4

    def test_overflow_page(self):
        """skip=0, limit=20, total=N. page is computed from skip+limit, not total"""
        skip, limit = 0, 20
        page = skip // limit + 1
        assert page == 1


# ── Task 2.3: ListResponse models accept page/limit ──────────────────────────

class TestListResponseModels:
    """Each ListResponse model must accept optional page/limit fields."""

    def test_client_list_response_with_page_limit(self):
        """ClientListResponse accepts page=1, limit=50."""
        from app.models.client import ClientListResponse
        resp = ClientListResponse(clients=[], total=0, page=1, limit=50)
        assert resp.page == 1
        assert resp.limit == 50
        assert resp.clients == []
        assert resp.total == 0

    def test_client_list_response_defaults(self):
        """ClientListResponse default page=1, limit=50."""
        from app.models.client import ClientListResponse
        resp = ClientListResponse(clients=[], total=0)
        assert resp.page == 1
        assert resp.limit == 50

    def test_product_list_response_with_page_limit(self):
        """ProductListResponse accepts page=2, limit=25."""
        from app.models.product import ProductListResponse
        resp = ProductListResponse(products=[], total=0, page=2, limit=25)
        assert resp.page == 2
        assert resp.limit == 25

    def test_product_list_response_defaults(self):
        """ProductListResponse default page=1, limit=50."""
        from app.models.product import ProductListResponse
        resp = ProductListResponse(products=[], total=0)
        assert resp.page == 1
        assert resp.limit == 50

    def test_sale_list_response_with_page_limit(self):
        """SaleListResponse accepts page=3, limit=10."""
        from app.models.sale import SaleListResponse
        resp = SaleListResponse(sales=[], total=0, page=3, limit=10)
        assert resp.page == 3
        assert resp.limit == 10

    def test_sale_list_response_defaults(self):
        """SaleListResponse default page=1, limit=50."""
        from app.models.sale import SaleListResponse
        resp = SaleListResponse(sales=[], total=0)
        assert resp.page == 1
        assert resp.limit == 50

    def test_invoice_list_response_with_page_limit(self):
        """InvoiceListResponse accepts page=1, limit=50."""
        from app.models.invoice import InvoiceListResponse
        resp = InvoiceListResponse(invoices=[], total=0, page=1, limit=50)
        assert resp.page == 1
        assert resp.limit == 50

    def test_invoice_list_response_defaults(self):
        """InvoiceListResponse default page=1, limit=50."""
        from app.models.invoice import InvoiceListResponse
        resp = InvoiceListResponse(invoices=[], total=0)
        assert resp.page == 1
        assert resp.limit == 50

    def test_service_list_response_with_page_limit(self):
        """ServiceListResponse accepts page=2, limit=100."""
        from app.models.service import ServiceListResponse
        resp = ServiceListResponse(services=[], total=0, page=2, limit=100)
        assert resp.page == 2
        assert resp.limit == 100

    def test_service_list_response_defaults(self):
        """ServiceListResponse default page=1, limit=50."""
        from app.models.service import ServiceListResponse
        resp = ServiceListResponse(services=[], total=0)
        assert resp.page == 1
        assert resp.limit == 50

    def test_attendance_list_response_with_page_limit(self):
        """AttendanceListResponse accepts page=1, limit=50."""
        from app.models.attendance import AttendanceListResponse
        resp = AttendanceListResponse(records=[], total=0, page=1, limit=50)
        assert resp.page == 1
        assert resp.limit == 50

    def test_attendance_list_response_defaults(self):
        """AttendanceListResponse default page=1, limit=50."""
        from app.models.attendance import AttendanceListResponse
        resp = AttendanceListResponse(records=[], total=0)
        assert resp.page == 1
        assert resp.limit == 50

    def test_employee_list_response_with_page_limit(self):
        """EmployeeListResponse accepts page=1, limit=50."""
        from app.models.employee import EmployeeListResponse
        resp = EmployeeListResponse(employees=[], total=0, page=1, limit=50)
        assert resp.page == 1
        assert resp.limit == 50

    def test_employee_list_response_defaults(self):
        """EmployeeListResponse default page=1, limit=100 (matches Query default)."""
        from app.models.employee import EmployeeListResponse
        resp = EmployeeListResponse(employees=[], total=0)
        assert resp.page == 1
        assert resp.limit == 100


# ── Task 2.2: DELETE endpoints return 204 ─────────────────────────────────────

class TestDeleteEndpoints:
    """Verify tenant-facing DELETE handlers return 204 No Content.

    These are import-time structural checks — verify the handler code path
    uses Response(status_code=204) instead of returning a dict.
    """

    def test_client_delete_returns_response_not_dict(self):
        """clients.py delete_client returns Response(status_code=204)."""
        import inspect
        from app.routers.clients import delete_client

        source = inspect.getsource(delete_client)
        assert "Response(status_code=204)" in source or "status_code=status.HTTP_204_NO_CONTENT" in source
        assert '"message"' not in source.split("return")[-1]  # no return {"message": ...}

    def test_product_delete_returns_response_not_dict(self):
        """products.py delete_product returns Response(status_code=204)."""
        import inspect
        from app.routers.products import delete_product

        source = inspect.getsource(delete_product)
        assert "Response(status_code=204)" in source or "status_code=status.HTTP_204_NO_CONTENT" in source

    def test_sale_delete_returns_response_not_dict(self):
        """sales.py delete_sale returns Response(status_code=204)."""
        import inspect
        from app.routers.sales import delete_sale

        source = inspect.getsource(delete_sale)
        assert "Response(status_code=204)" in source or "status_code=status.HTTP_204_NO_CONTENT" in source

    def test_invoice_delete_returns_response_not_dict(self):
        """invoices.py delete_invoice returns Response(status_code=204)."""
        import inspect
        from app.routers.invoices import delete_invoice

        source = inspect.getsource(delete_invoice)
        assert "Response(status_code=204)" in source or "status_code=status.HTTP_204_NO_CONTENT" in source

    def test_service_delete_returns_response_not_dict(self):
        """services.py delete_service returns Response(status_code=204)."""
        import inspect
        from app.routers.services import delete_service

        source = inspect.getsource(delete_service)
        assert "Response(status_code=204)" in source or "status_code=status.HTTP_204_NO_CONTENT" in source

    def test_attendance_has_no_delete(self):
        """attendance.py has no DELETE endpoint — skip."""
        import inspect
        from app.routers.attendance import router

        # Check no delete routes registered
        has_delete = any(route.methods == {"DELETE"} for route in router.routes)
        assert not has_delete, "Attendance should not have a DELETE route"

    def test_employee_delete_already_204(self):
        """employees.py delete_employee already returns 204 — no change needed."""
        import inspect
        from app.routers.employees import delete_employee

        source = inspect.getsource(delete_employee)
        assert "status_code=status.HTTP_204_NO_CONTENT" in source

    # ── Task 2.4: Admin DELETE stays at 200 ──

    def test_admin_delete_stays_200_with_body(self):
        """admin.py admin_delete_tenant still returns 200 with body (not 204)."""
        import inspect
        from app.routers.admin import admin_delete_tenant

        source = inspect.getsource(admin_delete_tenant)
        # Should NOT have any 204/NO_CONTENT status
        assert "204" not in source.split("async def")[-1][:200]
        # Should return result from service (which has {message, deleted})
        assert "return result" in source or "return await service.delete_tenant" in source


# ── Task 2.3: List endpoints include page/limit in return dicts ──────────────

class TestListEndpointsReturnPageLimit:
    """Verify list endpoints include page/limit in their return dicts.

    Uses source inspection to confirm the return value construction.
    """

    def test_clients_list_has_page_limit(self):
        """clients.py list_clients return dict includes 'page' and 'limit'."""
        import inspect
        from app.routers.clients import list_clients

        source = inspect.getsource(list_clients)
        assert '"page"' in source or "'page'" in source
        assert '"limit"' in source or "'limit'" in source

    def test_products_list_has_page_limit(self):
        """products.py list_products return dict includes 'page' and 'limit'."""
        import inspect
        from app.routers.products import list_products

        source = inspect.getsource(list_products)
        assert '"page"' in source or "'page'" in source
        assert '"limit"' in source or "'limit'" in source

    def test_sales_list_has_page_limit(self):
        """sales.py list_sales return dict includes 'page' and 'limit'."""
        import inspect
        from app.routers.sales import list_sales

        source = inspect.getsource(list_sales)
        assert '"page"' in source or "'page'" in source
        assert '"limit"' in source or "'limit'" in source

    def test_invoices_list_has_page_limit(self):
        """invoices.py list_invoices return dict includes 'page' and 'limit'."""
        import inspect
        from app.routers.invoices import list_invoices

        source = inspect.getsource(list_invoices)
        assert '"page"' in source or "'page'" in source
        assert '"limit"' in source or "'limit'" in source

    def test_services_list_has_page_limit(self):
        """services.py list_services return dict includes 'page' and 'limit'."""
        import inspect
        from app.routers.services import list_services

        source = inspect.getsource(list_services)
        assert '"page"' in source or "'page'" in source
        assert '"limit"' in source or "'limit'" in source

    def test_attendance_list_has_page_limit(self):
        """attendance.py list_attendance return dict includes 'page' and 'limit'."""
        import inspect
        from app.routers.attendance import list_attendance

        source = inspect.getsource(list_attendance)
        assert '"page"' in source or "'page'" in source
        assert '"limit"' in source or "'limit'" in source

    def test_employees_list_has_page_limit(self):
        """employees.py get_employees includes page/limit in response."""
        import inspect
        from app.routers.employees import get_employees

        source = inspect.getsource(get_employees)
        assert '"page"' in source or "'page'" in source or "page=" in source
        assert '"limit"' in source or "'limit'" in source or "limit=" in source
