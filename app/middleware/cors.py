"""ASGI middleware para CORS con soporte de credentials + Any origin.

Starlette CORSMiddleware no permite allow_origins=["*"] con allow_credentials=True
porque el spec de CORS lo prohibe explícitamente.

Este middleware refleja el Origin de la request en la respuesta, lo cual es
compatible con allow_credentials=True y efectivamente permite cualquier origen.
"""

from starlette.datastructures import MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

# Orígenes permitidos (configurables via ALLOWED_ORIGINS)
_ALLOWED_ORIGINS = [
    o.strip()
    for o in settings.ALLOWED_ORIGINS.split(",")
    if o.strip()
]
_ALLOW_WILDCARD = "*" in _ALLOWED_ORIGINS


class CORSMiddleware:
    """CORS middleware que refleja el Origin y permite credentials.

    - Si ALLOWED_ORIGINS=* (o no configurado): refleja cualquier Origin.
    - Si ALLOWED_ORIGINS tiene orígenes específicos: solo permite esos.

    Siempre incluye Access-Control-Allow-Credentials: true.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    @staticmethod
    def _get_origin(scope: Scope) -> str:
        for name, value in scope.get("headers", []):
            if name == b"origin":
                return value.decode(errors="replace")
        return ""

    @staticmethod
    def _origin_allowed(origin: str) -> bool:
        if not origin:
            return False
        if _ALLOW_WILDCARD:
            return True
        return origin in _ALLOWED_ORIGINS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origin = self._get_origin(scope)

        # ── Preflight (OPTIONS) ──
        if scope["method"] == "OPTIONS" and origin:
            if self._origin_allowed(origin):
                resp = PlainTextResponse(
                    "OK",
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Credentials": "true",
                        "Access-Control-Allow-Methods": (
                            "DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT"
                        ),
                        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin",
                        "Access-Control-Max-Age": "600",
                        "Vary": "Origin",
                    },
                )
                await resp(scope, receive, send)
                return

            # Origin no permitido → responder sin CORS
            await self.app(scope, receive, send)
            return

        # ── Requests normales ──
        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start" and self._origin_allowed(origin):
                m_headers = MutableHeaders(scope=message)
                m_headers["Access-Control-Allow-Origin"] = origin
                m_headers.add_vary_header("Origin")
                m_headers["Access-Control-Allow-Credentials"] = "true"
                m_headers["Access-Control-Expose-Headers"] = (
                    "Content-Type, Authorization, X-Requested-With"
                )
            await send(message)

        await self.app(scope, receive, _send)
