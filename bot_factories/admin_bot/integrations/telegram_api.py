import re
from typing import Any

import httpx

from bot_factories.admin_bot.config import admin_bot_settings
from shared.config import settings
from shared.managed_webhook import managed_bot_webhook_secret


def get_managed_bot_token(telegram_bot_id: int) -> str:
    if telegram_bot_id <= 0:
        raise ValueError("telegram_bot_id must be positive")
    token = _call(
        _admin_bot_token(),
        "getManagedBotToken",
        user_id=telegram_bot_id,
    )
    if not isinstance(token, str) or not token:
        raise RuntimeError("Telegram API returned an invalid managed bot token")
    return token


def configure_managed_bot_webhook(
    bot_token: str,
    telegram_bot_id: int,
) -> None:
    if not bot_token:
        raise ValueError("bot_token is required")
    if telegram_bot_id <= 0:
        raise ValueError("telegram_bot_id must be positive")
    if not admin_bot_settings.child_webhook_url:
        raise RuntimeError("ADMIN_BOT_CHILD_WEBHOOK_URL is required")
    if not settings.webhook_secret_token:
        raise RuntimeError("WEBHOOK_SECRET_TOKEN is required")

    _call(
        bot_token,
        "setWebhook",
        url=(
            f"{admin_bot_settings.child_webhook_url.rstrip('/')}"
            f"/{telegram_bot_id}"
        ),
        secret_token=managed_bot_webhook_secret(
            settings.webhook_secret_token,
            telegram_bot_id,
        ),
        allowed_updates=["message"],
    )


def _admin_bot_token() -> str:
    if not admin_bot_settings.token:
        raise RuntimeError("ADMIN_BOT_TOKEN is required")
    return admin_bot_settings.token


def _call(token: str, method: str, **payload: Any) -> Any:
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload,
            timeout=30,
        )
        body = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RuntimeError(f"Telegram API call failed: {method}") from error

    if not isinstance(body, dict):
        raise RuntimeError(f"Telegram API call failed: {method}; invalid response")

    if response.is_success and body.get("ok"):
        return body["result"]

    description = str(body.get("description", "unknown error")).replace(
        token, "[redacted]"
    )
    description = re.sub(r"(?:https?://|tg://)\S+", "[redacted]", description)
    raise RuntimeError(
        "Telegram API call failed: "
        f"{method}; code={body.get('error_code', response.status_code)} "
        f"description={description[:250]}"
    )
