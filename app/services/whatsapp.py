# Servicio de WhatsApp usando Twilio
"""WhatsApp notification service using Twilio"""
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Twilio es opcional - si no está instalado, el servicio no funciona
try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    Client = None


class WhatsAppService:
    """Servicio para enviar mensajes de WhatsApp via Twilio"""
    
    def __init__(self):
        self.client = None
        self.from_number = None
        
        if TWILIO_AVAILABLE and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            try:
                self.client = Client(
                    settings.TWILIO_ACCOUNT_SID,
                    settings.TWILIO_AUTH_TOKEN
                )
                self.from_number = settings.TWILIO_WHATSAPP_NUMBER
            except Exception as e:
                logger.warning(f"Twilio no configurado: {e}")
    
    def is_configured(self) -> bool:
        """Verificar si Twilio está configurado"""
        return self.client is not None
    
    async def send_message(self, to_number: str, message: str) -> dict:
        """Enviar mensaje de WhatsApp"""
        if not self.is_configured():
            logger.warning("Twilio no configurado")
            return {"status": "failed", "error": "Twilio not configured"}
        
        try:
            clean_number = "".join(filter(str.isdigit, to_number))
            if not clean_number.startswith("595"):
                clean_number = "595" + clean_number
            wa_number = f"+{clean_number}"
            
            twilio_msg = self.client.messages.create(
                from_=self.from_number,
                body=message,
                to=f"whatsapp:{wa_number}"
            )
            
            logger.info(f"WhatsApp enviado a {wa_number}: SID={twilio_msg.sid}")
            
            return {
                "status": "success",
                "sid": twilio_msg.sid,
                "to": wa_number
            }
            
        except Exception as e:
            logger.error(f"Error enviando WhatsApp: {e}")
            return {"status": "failed", "error": "Error interno del servicio de WhatsApp"}
    
    async def send_bulk(self, recipients: list[dict], message: str) -> dict:
        """Enviar mensaje a múltiples destinatarios"""
        results = []
        
        for recipient in recipients:
            phone = recipient.get("phone", "")
            if not phone:
                continue
            
            result = await self.send_message(phone, message)
            results.append({
                "phone": phone,
                "status": result["status"]
            })
        
        return {
            "total": len(recipients),
            "sent": sum(1 for r in results if r["status"] == "success"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
            "results": results
        }
    
    @staticmethod
    def format_message(template: str, variables: dict) -> str:
        """Formatear mensaje con variables"""
        message = template
        for key, value in variables.items():
            message = message.replace(f"{{{key}}}", str(value))
        return message


whatsapp_service = WhatsAppService()