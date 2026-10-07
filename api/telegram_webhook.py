import json
import logging
import hmac
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from shared.config import settings
from shared.managed_webhook import managed_bot_webhook_secret
from bot_factories.admin_bot.tasks import MANAGED_BOT_UPDATES_TASK
from worker.celery_app import celery_app
from worker.celery_factory import TELEGRAM_UPDATE_QUEUE, TELEGRAM_UPDATE_TASK

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
    celery_app.send_task(
        TELEGRAM_UPDATE_TASK,
        args=[body],
        queue=TELEGRAM_UPDATE_QUEUE,
    )

    logger.info("Task sent to Celery")

    return TelegramWebhookResponse(ok=True, detail="Message queued for processing")


@webhook_router.post(
    "/webhook/managed/{bot_id}", response_model=TelegramWebhookResponse
)
async def managed_bot_webhook(
    bot_id: int,
    body: dict[str, Any] = Body(...),
    telegram_secret_token: Optional[str] = Header(
        None, alias="X-Telegram-Bot-Api-Secret-Token", convert_underscores=False
    ),
):
    expected_secret = (
        managed_bot_webhook_secret(settings.webhook_secret_token, bot_id)
        if settings.webhook_secret_token
        else None
    )
    if (
        not expected_secret
        or not telegram_secret_token
        or not hmac.compare_digest(telegram_secret_token, expected_secret)
    ):
        logger.warning("Forbidden managed-bot webhook: bot_id=%s", bot_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    celery_app.send_task(
        MANAGED_BOT_UPDATES_TASK,
        args=[bot_id, body],
        queue=TELEGRAM_UPDATE_QUEUE,
    )
    return TelegramWebhookResponse(ok=True, detail="Managed bot update queued")
