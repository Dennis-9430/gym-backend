"""Servicio de email transaccional usando Resend."""

import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Inicialización lazy de Resend — solo si hay API key configurada
_resend_available = False


def _init_resend():
    global _resend_available
    if settings.RESEND_API_KEY:
        try:
            import resend
            resend.api_key = settings.RESEND_API_KEY
            _resend_available = True
            logger.info("Resend inicializado correctamente")
        except Exception as e:
            logger.warning("No se pudo inicializar Resend: %s. Los emails se loguearán por consola.", e)
            _resend_available = False
    else:
        logger.info("RESEND_API_KEY no configurada. Los emails se loguearán por consola.")
        _resend_available = False


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: str = "",
) -> bool:
    """Envía un email transaccional vía Resend.
    
    Si Resend no está configurado, loguea el contenido por consola (modo dev).
    
    Returns:
        True si se envió (o logueó) correctamente, False si falló.
    """
    if not _resend_available:
        _init_resend()

    if not _resend_available:
        logger.info("[EMAIL - MODO DEV] Para: %s | Asunto: %s\n%s", to, subject, html)
        return True

    try:
        import resend
        params = {
            "from": settings.EMAIL_FROM,
            "to": to,
            "subject": subject,
            "html": html,
        }
        if text:
            params["text"] = text

        response = resend.Emails.send(params)
        logger.info("Email enviado a %s | id=%s", to, response.get("id", "unknown"))
        return True

    except Exception as e:
        logger.error("Error enviando email a %s: %s", to, e)
        return False


async def send_password_reset_email(to: str, reset_link: str, business_name: str) -> bool:
    """Envía email de recuperación de contraseña."""
    subject = f"Recuperación de contraseña — {business_name}"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; padding: 24px; background: #f4f4f5;">
        <div style="max-width: 480px; margin: 0 auto; background: white; border-radius: 8px; padding: 32px;">
            <h2 style="color: #1f2937; margin-top: 0;">Recuperación de contraseña</h2>
            <p style="color: #4b5563; line-height: 1.6;">
                Recibiste este correo porque solicitaste restablecer tu contraseña
                en <strong>{business_name}</strong>.
            </p>
            <p style="text-align: center; margin: 32px 0;">
                <a href="{reset_link}"
                   style="background: #2563eb; color: white; padding: 12px 24px;
                          border-radius: 6px; text-decoration: none; font-weight: bold;
                          display: inline-block;">
                    Restablecer contraseña
                </a>
            </p>
            <p style="color: #6b7280; font-size: 14px;">
                Este enlace expira en <strong>15 minutos</strong>.
                Si no solicitaste este cambio, ignorá este mensaje.
            </p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
            <p style="color: #9ca3af; font-size: 12px;">
                Gym Management — {business_name}
            </p>
        </div>
    </body>
    </html>
    """
    text = (
        f"Recuperación de contraseña — {business_name}\n\n"
        f"Restablecé tu contraseña en este enlace: {reset_link}\n\n"
        f"Este enlace expira en 15 minutos."
    )
    return await send_email(to=to, subject=subject, html=html, text=text)
