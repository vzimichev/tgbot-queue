import json
import logging
import secrets
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from shared.config import settings
from worker.celery_app import celery_app
from bot_factories.admin_bot.config import admin_settings
from shared.bot_registry import (
    BotRegistry,
    ADMIN_TASK,
    ADMIN_QUEUE,
    MANAGED_ECHO_TASK,
    MANAGED_ECHO_QUEUE,
)

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
        logger.warning("Forbidden request with invalid secret token")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Log incoming request
    logger.info("Incoming webhook body: %s", json.dumps(body))

    # Send the JSON to Celery
    celery_app.send_task(
        settings.telegram_task_name,
        args=[body],
        queue=settings.telegram_queue,
    )

    logger.info("Task sent to Celery")

    return TelegramWebhookResponse(ok=True, detail="Message queued for processing")


def require_secret(expected, actual):
    if (
        not expected
        or not actual
        or not secrets.compare_digest(expected.encode(), actual.encode())
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


@webhook_router.post("/webhook/admin", response_model=TelegramWebhookResponse)
def admin_webhook(
    body: dict[str, Any] = Body(...),
    secret: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    require_secret(admin_settings.webhook_secret, secret)
    celery_app.send_task(ADMIN_TASK, args=[body], queue=ADMIN_QUEUE)
    return TelegramWebhookResponse(ok=True)


@webhook_router.post(
    "/webhook/managed/{bot_id}", response_model=TelegramWebhookResponse
)
def managed_webhook(
    bot_id: int,
    body: dict[str, Any] = Body(...),
    secret: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    record = BotRegistry().get(bot_id)
    if not record or record["status"] != "active" or record["kind"] != "echo":
        raise HTTPException(status_code=404, detail="Bot unavailable")
    require_secret(record["secret"], secret)
    celery_app.send_task(
        MANAGED_ECHO_TASK, args=[bot_id, body], queue=MANAGED_ECHO_QUEUE
    )
    return TelegramWebhookResponse(ok=True)
