# Utilidades de sanitización para seguridad
# Relacionado con: routers/clients.py, routers/products.py
"""Sanitization utilities for security"""
import re
import asyncio

# Límites de seguridad
MAX_SEARCH_LENGTH = 50
SEARCH_TIMEOUT_MS = 1000  # 1 segundo max

# Solo letras, números, espacios y guiones (caracteres seguros para búsqueda)
ALLOWED_PATTERN = re.compile(r'^[a-zA-Z0-9\sáéíóúñÁÉÍÓÚüÜ\-]+$')


def sanitize_search_input(input: str) -> str | None:
    """Sanitiza input de búsqueda - búsqueda exacta
    
    Previene:
    - Inyección Regex DoS
    - Inyección de caracteres especiales
    - Búsquedas excesivamente largas
    
    Args:
        input: Texto a sanitizar
        
    Returns:
        Texto sanitizado o None si es inválido
    """
    if not input:
        return None
    
    # Recortar whitespace extremo y limitar longitud
    sanitized = input.strip()[:MAX_SEARCH_LENGTH]
    
    # Validar que solo tenga caracteres permitidos
    if not ALLOWED_PATTERN.match(sanitized):
        return None
    
    return sanitized


def sanitize_document_number(input: str) -> str | None:
    """Sanitiza número de documento (cédula)
    
    Solo permite números y guiones (formato Cédula).
    """
    if not input:
        return None
    
    sanitized = input.strip()[:20]  # Máx 20 caracteres
    
    # Solo números y guiones
    pattern = re.compile(r'^[0-9\-]+$')
    if not pattern.match(sanitized):
        return None
    
    return sanitized


async def search_with_timeout(coro, timeout_ms: int = SEARCH_TIMEOUT_MS):
    """Ejecuta búsqueda con timeout para prevenir DoS
    
    Args:
        coro: Corrutina async a ejecutar
        timeout_ms: Timeout en milisegundos
        
    Returns:
        Resultado de la corrutina o lista vacía en timeout
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_ms / 1000)
    except asyncio.TimeoutError:
        return []