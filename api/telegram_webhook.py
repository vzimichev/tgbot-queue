import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from shared.config import settings
from worker.celery_app import celery_app

webhook_router = APIRouter()
logger = logging.getLogger("telegram_webhook")


class TelegramWebhookResponse(BaseModel):
    ok: bool
    detail: Optional[str] = None


@webhook_router.post("/webhook", response_model=TelegramWebhookResponse)
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

    # Log incoming request
    logger.info("Incoming webhook body: %s", json.dumps(body))

    # Send the JSON to Celery
    celery_app.send_task("process_telegram_task", args=[body])

    logger.info("Task sent to Celery")

    return TelegramWebhookResponse(ok=True, detail="Message queued for processing")
