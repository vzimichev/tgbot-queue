import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import settings
from app.services.telegram import send_message

router = APIRouter()

# Configure logging
logger = logging.getLogger("telegram_webhook")
logger.setLevel(logging.INFO)


class TelegramWebhookResponse(BaseModel):
    ok: bool
    detail: Optional[str] = None


import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.services.rabbitmq import rabbit
from app.services.telegram import send_message

router = APIRouter()

logger = logging.getLogger("telegram_webhook")
logger.setLevel(logging.INFO)


class TelegramWebhookResponse(BaseModel):
    ok: bool
    detail: Optional[str] = None


@router.post("/webhook", response_model=TelegramWebhookResponse)
async def telegram_webhook(
    body: dict[str, Any] = Body(...),
    telegram_secret_token: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token", convert_underscores=False
    ),
):
    # Validate secret token
    if (
        settings.webhook_secret_token
        and telegram_secret_token != settings.webhook_secret_token
    ):
        logger.warning(
            "Forbidden request with invalid secret token: %s", telegram_secret_token
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Log
    logger.info("Incoming webhook body: %s", json.dumps(body, ensure_ascii=False))

    # Send to RabbitMQ
    rabbit.publish(body)
    logger.info("Webhook forwarded to RabbitMQ queue 'telegram_updates'")

    # Process message if exists
    message = body.get("message")
    if not message:
        return TelegramWebhookResponse(ok=True, detail="No message to process")

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    response_text = f"You said: {text}"
    await send_message(chat_id, response_text)

    return TelegramWebhookResponse(ok=True, detail="Message processed successfully")
