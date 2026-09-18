import json
import logging
import secrets
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from api.admin_webhook import process_admin_update
from bot_factories.admin_bot.config import admin_settings
from shared.config import settings

webhook_router = APIRouter()
logger = logging.getLogger("telegram_webhook")


class TelegramWebhookResponse(BaseModel):
    ok: bool
    detail: Optional[str] = None


@webhook_router.post("/webhook", response_model=TelegramWebhookResponse)
def telegram_webhook(
    body: dict[str, Any] = Body(...),
    telegram_secret_token: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token", convert_underscores=False
    ),
):
    admin_secret = admin_settings.webhook_secret.get_secret_value()
    if (
        telegram_secret_token
        and admin_secret
        and secrets.compare_digest(telegram_secret_token, admin_secret)
    ):
        process_admin_update(body)
        return TelegramWebhookResponse(ok=True, detail="Admin update processed")
    if not (
        telegram_secret_token
        and settings.webhook_secret_token
        and secrets.compare_digest(telegram_secret_token, settings.webhook_secret_token)
    ):
        logger.warning("Forbidden webhook request")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Log incoming request
    logger.info("Incoming webhook body: %s", json.dumps(body))

    # Send the JSON to Celery
    from worker.celery_app import celery_app

    celery_app.send_task(
        settings.telegram_task_name,
        args=[body],
        queue=settings.telegram_queue,
    )

    logger.info("Task sent to Celery")

    return TelegramWebhookResponse(ok=True, detail="Message queued for processing")
