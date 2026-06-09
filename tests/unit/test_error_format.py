"""Tests for standardized API error format — models, handlers, and backward compatibility."""
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport
from pydantic import BaseModel, ValidationError


class TestAPIErrorModels:
    """Unit tests for APIError model — no FastAPI app needed."""

    def test_api_error_detail_requires_all_fields(self):
        """APIErrorDetail requires code, detail, message."""
        from app.models.error import APIErrorDetail

        err = APIErrorDetail(code="NOT_FOUND", detail="Not found", message="Not found")
        assert err.code == "NOT_FOUND"
        assert err.detail == "Not found"
        assert err.message == "Not found"

    def test_api_error_detail_serializes_correctly(self):
        """APIErrorDetail.model_dump() produces expected dict."""
        from app.models.error import APIErrorDetail

        err = APIErrorDetail(code="NOT_FOUND", detail="Item no encontrado", message="Item no encontrado")
        dumped = err.model_dump()
        assert dumped == {
            "code": "NOT_FOUND",
            "detail": "Item no encontrado",
            "message": "Item no encontrado",
        }

    def test_api_error_detail_cannot_be_empty(self):
        """APIErrorDetail rejects empty required fields."""
        from app.models.error import APIErrorDetail

        with pytest.raises(ValidationError):
            APIErrorDetail()

    def test_api_error_wraps_detail(self):
        """APIError wraps APIErrorDetail under 'error' key."""
        from app.models.error import APIError, APIErrorDetail

        detail = APIErrorDetail(code="UNAUTHORIZED", detail="Bad creds", message="Bad creds")
        err = APIError(error=detail)
        dumped = err.model_dump()
        assert dumped == {
            "error": {
                "code": "UNAUTHORIZED",
                "detail": "Bad creds",
                "message": "Bad creds",
            }
        }

    def test_api_error_roundtrip(self):
        """APIError.model_dump() -> dict is the final JSON shape sent to frontend."""
        from app.models.error import APIError, APIErrorDetail

        payload = APIError(
            error=APIErrorDetail(code="NOT_FOUND", detail="Tenant no encontrado", message="Tenant no encontrado")
        ).model_dump()
        assert "error" in payload
        assert payload["error"]["code"] == "NOT_FOUND"
        assert payload["error"]["detail"] == "Tenant no encontrado"


class TestErrorCodes:
    """ErrorCodes constants are accessible."""

    def test_error_codes_class_has_expected_codes(self):
        """All expected error codes are defined."""
        from app.models.error import ErrorCodes

        assert ErrorCodes.INTERNAL_ERROR == "INTERNAL_ERROR"
        assert ErrorCodes.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert ErrorCodes.NOT_FOUND == "NOT_FOUND"
        assert ErrorCodes.UNAUTHORIZED == "UNAUTHORIZED"
        assert ErrorCodes.FORBIDDEN == "FORBIDDEN"
        assert ErrorCodes.CONFLICT == "CONFLICT"
        assert ErrorCodes.RATE_LIMITED == "RATE_LIMITED"
        assert ErrorCodes.TENANT_NOT_FOUND == "TENANT_NOT_FOUND"
        assert ErrorCodes.USER_NOT_FOUND == "USER_NOT_FOUND"
        assert ErrorCodes.PAYMENT_REQUIRED == "PAYMENT_REQUIRED"
        assert ErrorCodes.CSRF_ERROR == "CSRF_ERROR"


@pytest.mark.asyncio
class TestHTTPExceptionHandler:
    """Integration tests for the custom HTTPException handler — uses minimal TestClient."""

    @pytest.fixture
    def test_app(self):
        """A minimal FastAPI app with the custom handler + routes that raise HTTPException."""
        from app.models.error import APIError, APIErrorDetail, ErrorCodes
        from fastapi.responses import JSONResponse

        api = FastAPI()

        STATUS_CODE_MAP = {
            400: ErrorCodes.VALIDATION_ERROR,
            401: ErrorCodes.UNAUTHORIZED,
            403: ErrorCodes.FORBIDDEN,
            404: ErrorCodes.NOT_FOUND,
            409: ErrorCodes.CONFLICT,
            422: ErrorCodes.VALIDATION_ERROR,
            429: ErrorCodes.RATE_LIMITED,
            500: ErrorCodes.INTERNAL_ERROR,
        }

        @api.exception_handler(HTTPException)
        async def http_exception_handler(request, exc):
            detail = exc.detail
            code = STATUS_CODE_MAP.get(exc.status_code, ErrorCodes.INTERNAL_ERROR)
            message = detail if isinstance(detail, str) else str(detail)
            return JSONResponse(
                status_code=exc.status_code,
                content=APIError(
                    error=APIErrorDetail(code=code, detail=message, message=message)
                ).model_dump(),
            )

        @api.get("/not-found")
        async def not_found():
            raise HTTPException(status_code=404, detail="Tenant no encontrado")

        @api.get("/unauthorized")
        async def unauthorized():
            raise HTTPException(status_code=401, detail="Credenciales incorrectas")

        @api.get("/forbidden")
        async def forbidden():
            raise HTTPException(status_code=403, detail="Acceso denegado")

        @api.get("/conflict")
        async def conflict():
            raise HTTPException(status_code=409, detail="Conflicto de datos")

        @api.get("/server-error")
        async def server_error():
            raise HTTPException(status_code=500, detail="Error interno")

        return api

    async def test_404_includes_error_key(self, test_app):
        """404 response contains 'error' key with code, detail, message."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/not-found")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "NOT_FOUND"

    async def test_404_detail_is_present(self, test_app):
        """Backward compatibility: 'detail' field is present at error.detail."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/not-found")
        data = resp.json()
        assert "detail" in data["error"]
        assert data["error"]["detail"] == "Tenant no encontrado"

    async def test_404_message_matches_detail(self, test_app):
        """message matches detail for backward compat (frontend reads both)."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/not-found")
        data = resp.json()
        assert data["error"]["message"] == data["error"]["detail"]

    async def test_401_includes_error_key(self, test_app):
        """401 response uses standardized format."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/unauthorized")
        assert resp.status_code == 401
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "UNAUTHORIZED"
        assert "detail" in data["error"]

    async def test_403_includes_error_key(self, test_app):
        """403 response uses standardized format."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/forbidden")
        assert resp.status_code == 403
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "FORBIDDEN"
        assert "detail" in data["error"]

    async def test_409_includes_error_key(self, test_app):
        """409 response uses standardized format."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/conflict")
        assert resp.status_code == 409
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "CONFLICT"
        assert "detail" in data["error"]

    async def test_500_includes_error_key(self, test_app):
        """500 response uses standardized format."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/server-error")
        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert "detail" in data["error"]

    async def test_frontend_reads_detail_or_message(self, test_app):
        """Simulate frontend's data?.detail || data?.message pattern."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/unauthorized")
        data = resp.json()
        error = data.get("error", {})
        text = error.get("detail") or error.get("message")
        assert text is not None
        assert text == "Credenciales incorrectas"

    async def test_unmapped_status_code_falls_back_to_internal_error(self, test_app):
        """Status codes not in the map use INTERNAL_ERROR."""
        # Test with a route that returns status 402 (not in map)
        from fastapi.responses import JSONResponse

        @test_app.get("/payment-required")
        async def payment_required():
            raise HTTPException(status_code=402, detail="Payment needed")

        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/payment-required")
        assert resp.status_code == 402
        data = resp.json()
        assert data["error"]["code"] == "INTERNAL_ERROR"

    async def test_detail_with_non_string_handled_safely(self, test_app):
        """Non-string detail (e.g. dict) is converted to string."""
        from fastapi.responses import JSONResponse

        @test_app.get("/dict-detail")
        async def dict_detail():
            raise HTTPException(status_code=400, detail={"field": "name", "reason": "required"})

        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.get("/dict-detail")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "field" in data["error"]["detail"] or "name" in data["error"]["detail"]


@pytest.mark.asyncio
class TestValidationErrorHandler:
    """Integration tests for RequestValidationError handler."""

    @pytest.fixture
    def test_app(self):
        from app.models.error import APIError, APIErrorDetail, ErrorCodes
        from fastapi.responses import JSONResponse

        api = FastAPI()

        @api.exception_handler(RequestValidationError)
        async def validation_exception_handler(request, exc):
            return JSONResponse(
                status_code=422,
                content=APIError(
                    error=APIErrorDetail(
                        code=ErrorCodes.VALIDATION_ERROR,
                        detail=str(exc),
                        message="Error de validación"
                    )
                ).model_dump(),
            )

        class InputData(BaseModel):
            name: str
            age: int

        @api.post("/validate")
        async def validate(data: InputData):
            return {"ok": True}

        return api

    async def test_422_includes_error_key(self, test_app):
        """422 response has standardized error format."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post("/validate", json={"name": "test"})  # missing age
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"

    async def test_422_has_detail_field(self, test_app):
        """422 response includes detail field."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post("/validate", json={"name": "test"})
        data = resp.json()
        assert "detail" in data["error"]
        assert "age" in data["error"]["detail"].lower() or "field required" in data["error"]["detail"].lower()

    async def test_422_has_message_in_spanish(self, test_app):
        """422 message is 'Error de validación'."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post("/validate", json={"name": "test"})
        data = resp.json()
        assert data["error"]["message"] == "Error de validación"

    async def test_422_backward_compatible_detail(self, test_app):
        """Frontend can read detail from 422 errors via data?.detail || data?.message."""
        async with httpx.AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post("/validate", json={"name": "test"})
        data = resp.json()
        error = data.get("error", {})
        text = error.get("detail") or error.get("message")
        assert text is not None


@pytest.mark.asyncio
class TestCatchAllMiddleware:
    """Tests the CatchAllErrorMiddleware includes detail field."""

    async def test_catch_all_includes_detail(self):
        """Unhandled exceptions return error with detail field."""
        from app.main import CatchAllErrorMiddleware

        app = FastAPI()

        @app.get("/crash")
        async def crash():
            raise RuntimeError("Algo salió mal")

        app.add_middleware(CatchAllErrorMiddleware)

        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/crash")
        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data
        assert "detail" in data["error"]
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert data["error"]["message"] == "Error interno del servidor"

    async def test_catch_all_has_message(self):
        """Unhandled exceptions have message field."""
        from app.main import CatchAllErrorMiddleware

        app = FastAPI()

        @app.get("/panic")
        async def panic():
            raise ValueError("Panic!")

        app.add_middleware(CatchAllErrorMiddleware)

        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/panic")
        data = resp.json()
        assert data["error"]["message"] == "Error interno del servidor"
