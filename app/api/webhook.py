import logging
from typing import Optional, Any

from fastapi import APIRouter, Header, HTTPException, Request, status, Body
from pydantic import BaseModel

from app.core.config import settings
from app.services.telegram import send_message

router = APIRouter()

# Configure logging
logger = logging.getLogger("telegram_webhook")
logging.basicConfig(level=logging.INFO)


class TelegramWebhookResponse(BaseModel):
    ok: bool
    detail: Optional[str] = None


@router.post("/webhook", response_model=TelegramWebhookResponse)
async def telegram_webhook(
    body: dict[str, Any] = Body(...),
    telegram_secret_token: str = Header(convert_underscores=False),
):
    # Log incoming request
    logger.info("Incoming webhook body: %s", body)

    # Validate secret token
    if (
        settings.webhook_secret_token
        and telegram_secret_token != settings.webhook_secret_token
    ):
        logger.warning(
            "Forbidden request with invalid secret token: %s", telegram_secret_token
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    message = body.get("message")
    if not message:
        logger.info("No message found in update: %s", body)
        return TelegramWebhookResponse(ok=True, detail="No message to process")

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    # Log what will be sent
    response_text = f"You said: {text}"
    logger.info("Sending message to chat_id %s: %s", chat_id, response_text)

    # Send message
    await send_message(chat_id, response_text)

    logger.info("Message sent successfully")

    return TelegramWebhookResponse(ok=True, detail="Message processed successfully")
