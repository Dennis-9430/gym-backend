"""Servicio de email transaccional usando Brevo (ex Sendinblue)."""

import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Inicialización lazy de Brevo — solo si hay API key configurada
_brevo_available = False


def _init_brevo():
    global _brevo_available
    if settings.BREVO_API_KEY:
        try:
            import sib_api_v3_sdk
            _brevo_available = True
            logger.info("Brevo inicializado correctamente")
        except Exception as e:
            logger.warning("No se pudo inicializar Brevo: %s. Los emails se loguearán por consola.", e)
            _brevo_available = False
    else:
        logger.info("BREVO_API_KEY no configurada. Los emails se loguearán por consola.")
        _brevo_available = False


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: str = "",
) -> bool:
    """Envía un email transaccional vía Brevo (ex Sendinblue).
    
    Si Brevo no está configurado, loguea el contenido por consola (modo dev).
    
    Returns:
        True si se envió (o logueó) correctamente, False si falló.
    """
    if not _brevo_available:
        _init_brevo()

    if not _brevo_available:
        logger.info("[EMAIL - MODO DEV] Para: %s | Asunto: %s\n%s", to, subject, html)
        return True

    try:
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key["api-key"] = settings.BREVO_API_KEY

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )

        send_obj = sib_api_v3_sdk.SendSmtpEmail(
            to=[sib_api_v3_sdk.SendSmtpEmailTo(email=to)],
            sender=sib_api_v3_sdk.SendSmtpEmailSender(
                email=settings.EMAIL_FROM,
                name=settings.EMAIL_FROM_NAME,
            ),
            subject=subject,
            html_content=html,
            text_content=text or None,
        )

        result = api_instance.send_transac_email(send_obj)
        logger.info("Email enviado a %s | message_id=%s", to, result.message_id)
        return True

    except ApiException as e:
        logger.error("Error Brevo API enviando email a %s: %s", to, e)
        return False
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


async def send_welcome_owner_email(to: str, owner_name: str, business_name: str) -> bool:
    """Envía email de bienvenida al owner después de registrar su gimnasio."""
    subject = f"¡Bienvenido a Gym Management — {business_name}!"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; padding: 24px; background: #f4f4f5;">
        <div style="max-width: 480px; margin: 0 auto; background: white; border-radius: 8px; padding: 32px;">
            <h2 style="color: #1f2937; margin-top: 0;">¡Felicitaciones, {owner_name}!</h2>
            <p style="color: #4b5563; line-height: 1.6;">
                Has registrado <strong>{business_name}</strong> exitosamente en Gym Management.
            </p>
            <p style="color: #4b5563; line-height: 1.6;">
                Ya podés iniciar sesión con tu correo electrónico y la contraseña que elegiste
                para comenzar a gestionar tu gimnasio.
            </p>
            <p style="color: #6b7280; font-size: 14px;">
                Si tenés alguna duda, respondé a este correo.
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
        f"Bienvenido a Gym Management — {business_name}\n\n"
        f"Has registrado {business_name} exitosamente.\n\n"
        f"Iniciá sesión con tu correo y contraseña para gestionar tu gimnasio."
    )
    return await send_email(to=to, subject=subject, html=html, text=text)


async def send_welcome_employee_email(to: str, name: str, username: str, password: str, business_name: str) -> bool:
    """Envía email de bienvenida a un nuevo empleado con sus credenciales."""
    subject = f"Bienvenido a {business_name} — Tus credenciales de acceso"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; padding: 24px; background: #f4f4f5;">
        <div style="max-width: 480px; margin: 0 auto; background: white; border-radius: 8px; padding: 32px;">
            <h2 style="color: #1f2937; margin-top: 0;">¡Bienvenido, {name}!</h2>
            <p style="color: #4b5563; line-height: 1.6;">
                Te han dado de alta como empleado en <strong>{business_name}</strong>.
                Usá estas credenciales para iniciar sesión:
            </p>
            <div style="background: #f3f4f6; border-radius: 8px; padding: 16px; margin: 20px 0;">
                <p style="margin: 4px 0; font-size: 14px; color: #374151;">
                    <strong>Usuario:</strong> {username}
                </p>
                <p style="margin: 4px 0; font-size: 14px; color: #374151;">
                    <strong>Contraseña:</strong> {password}
                </p>
            </div>
            <p style="color: #6b7280; font-size: 14px;">
                Te recomendamos cambiar tu contraseña después del primer inicio de sesión.
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
        f"Bienvenido a {business_name}\n\n"
        f"Te han dado de alta como empleado.\n"
        f"Usuario: {username}\n"
        f"Contraseña: {password}\n\n"
        f"Cambiá tu contraseña después del primer inicio de sesión."
    )
    return await send_email(to=to, subject=subject, html=html, text=text)


async def send_welcome_client_email(to: str, client_name: str, business_name: str) -> bool:
    """Envía email de bienvenida a un nuevo cliente del gimnasio."""
    subject = f"¡Bienvenido a {business_name}!"
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; padding: 24px; background: #f4f4f5;">
        <div style="max-width: 480px; margin: 0 auto; background: white; border-radius: 8px; padding: 32px;">
            <h2 style="color: #1f2937; margin-top: 0;">¡Bienvenido, {client_name}!</h2>
            <p style="color: #4b5563; line-height: 1.6;">
                Te hemos registrado como cliente en <strong>{business_name}</strong>.
                Ya estás listo para disfrutar de nuestros servicios.
            </p>
            <p style="color: #4b5563; line-height: 1.6;">
                    Cualquier consulta, no dudes en contactarnos.
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
        f"Bienvenido a {business_name}\n\n"
        f"Te hemos registrado como cliente. Cualquier consulta, contactanos."
    )
    return await send_email(to=to, subject=subject, html=html, text=text)
