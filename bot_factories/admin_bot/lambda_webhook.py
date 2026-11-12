"""API Gateway HTTP API (payload v2) entry point for admin and managed bots.

Runtime configuration supplies WEBHOOK_SECRET_TOKEN and the existing SQS
settings. Secret retrieval and infrastructure are deployment responsibilities.
"""

import base64
import binascii
import hmac
import json
import logging
import os
import re
from functools import lru_cache

from aiogram.types import Update
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from shared.config import settings
from shared.managed_webhook import managed_bot_webhook_secret
from worker.celery_app import celery_app
from worker.celery_factory import TELEGRAM_UPDATE_TASK

logger = logging.getLogger(__name__)


class GatewayHttpRequest(BaseModel):
    method: str
    path: str


class GatewayRequestContext(BaseModel):
    http: GatewayHttpRequest


class GatewayEvent(BaseModel):
    # AWS may add metadata without changing this handler's contract.
    model_config = ConfigDict(extra="ignore", strict=True)

    request_context: GatewayRequestContext = Field(alias="requestContext")
    headers: dict[str, str | None] | None = None
    body: str
    is_base64_encoded: bool = Field(default=False, alias="isBase64Encoded")


class WebhookUpdate(Update):
    update_id: StrictInt


def handler(event: dict, context) -> dict:
    try:
        request = GatewayEvent.model_validate(event)
    except ValidationError:
        return _response(400, False)

    http = request.request_context.http
    if http.method != "POST":
        return _response(405, False)

    path = http.path
    managed = re.fullmatch(r"/webhook/managed/([1-9][0-9]{0,18})", path)
    if path != "/webhook" and managed is None:
        return _response(404, False)

    # Fail closed on missing deployment configuration; never fall back to Redis.
    try:
        secret = _webhook_secret()
    except Exception:
        logger.error("Webhook secret retrieval failed")
        return _response(503, False)
    if not secret or settings.celery_broker.lower() != "sqs":
        logger.error("Webhook runtime configuration is incomplete")
        return _response(503, False)

    bot_id = int(managed.group(1)) if managed else None
    expected = (
        managed_bot_webhook_secret(secret, bot_id)
        if bot_id is not None
        else secret
    )
    headers = {k.lower(): v for k, v in (request.headers or {}).items()}
    supplied = headers.get("x-telegram-bot-api-secret-token")
    if supplied is None or not hmac.compare_digest(
        supplied.encode(), expected.encode()
    ):
        return _response(403, False)

    try:
        body = request.body
        if request.is_base64_encoded:
            body = base64.b64decode(body, validate=True).decode("utf-8")
        WebhookUpdate.model_validate_json(body)
        # Forward the original JSON, retaining unknown Telegram fields and
        # avoiding model defaults or datetime conversions in the queue payload.
        update = json.loads(body)
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return _response(400, False)

    try:
        celery_app.send_task(
            "managed_bot.updates" if bot_id is not None else TELEGRAM_UPDATE_TASK,
            args=[bot_id, update] if bot_id is not None else [update],
            queue=settings.sqs_queue_name,
            retry=False,
        )
    except Exception:
        # Exception text can contain request/configuration data. Log no secrets.
        logger.error("Webhook task publication failed")
        return _response(503, False)
    return _response(200, True)


def _response(status: int, ok: bool) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"ok": ok}),
    }


def _webhook_secret() -> str:
    secret_arn = os.getenv("WEBHOOK_SECRET_ARN")
    if not secret_arn:
        return settings.webhook_secret_token or ""
    return _read_secret(secret_arn)


@lru_cache(maxsize=1)
def _read_secret(secret_arn: str) -> str:
    import boto3

    return boto3.client("secretsmanager").get_secret_value(
        SecretId=secret_arn
    )["SecretString"]
