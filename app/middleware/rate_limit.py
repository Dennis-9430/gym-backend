# Middleware de rate limiting simple
# Relacionado con: main.py
"""
Simple rate limiting middleware

╔══════════════════════════════════════════════════════════════════════════╗
║  PENDIENTE: Rate limit con Redis                                        ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Este rate limiter usa almacenamiento en memoria (dict), que no         ║
║  funciona en multi-instancia ni sobrevive reinicios.                    ║
║                                                                         ║
║  Para producción con múltiples workers o instancias:                    ║
║  1. Instalar redis-py y configurar REDIS_URL en .env                    ║
║  2. Reemplazar _rate_limit_store por Redis (ej: redis-py + incr/expire) ║
║  3. Mantener este módulo como fallback local si REDIS_URL no está set   ║
║                                                                         ║
║  Referencia: app/middleware/rate_limit.py, app/config.py                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import time
from typing import Dict, Tuple
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Configuración de límites
# Relacionado con: main.py
DEFAULT_RATE_LIMIT = 2000  # Requests por minute
LOGIN_RATE_LIMIT = 10     # Intentos de login por minute

# Almacenamiento simple en memoria (en producción usar Redis)
# Relacionado con: rate_limit_store
_rate_limit_store: Dict[str, Tuple[int, float]] = {}


def get_client_ip(request: Request) -> str:
    """Obtiene IP del cliente - soporte para proxies"""
    # X-Forwarded-For para deployments con proxy
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    client_id: str, 
    limit: int = DEFAULT_RATE_LIMIT,
    window: int = 60
) -> bool:
    """Verifica rate limit para un cliente
    
    Args:
        client_id: Identificador único del cliente (IP o user)
        limit: Número máximo de requests
        window: Ventana de tiempo en segundos
        
    Returns:
        True si está dentro del límite, False si excedido
    """
    now = time.time()
    current = _rate_limit_store.get(client_id)
    
    if current is None:
        _rate_limit_store[client_id] = (1, now)
        return True
    
    count, start_time = current
    
    # Reset si pasó la ventana de tiempo
    if now - start_time > window:
        _rate_limit_store[client_id] = (1, now)
        return True
    
    # Incrementar contador
    if count < limit:
        _rate_limit_store[client_id] = (count + 1, start_time)
        return True
    
    return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware de rate limiting para FastAPI"""
    
    def __init__(self, app, rate_limit: int = DEFAULT_RATE_LIMIT):
        super().__init__(app)
        self.rate_limit = rate_limit
    
    async def dispatch(self, request: Request, call_next):
        # No aplicar rate limit a OPTIONS (preflight CORS)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Rutas exemptas (no rate limit)
        exempt_paths = ["/", "/health", "/docs", "/openapi.json"]
        if request.url.path in exempt_paths:
            return await call_next(request)
        
        # Verificar rate limit
        client_id = get_client_ip(request)
        
        if not check_rate_limit(client_id, self.rate_limit):
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later."
            )
        
        return await call_next(request)