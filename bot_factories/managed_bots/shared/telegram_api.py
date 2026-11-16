import re
from typing import Any

import httpx

from bot_factories.managed_bots.shared.managed_webhook import managed_bot_webhook_secret


def get_managed_bot_token(telegram_bot_id: int, *, admin_token: str | None) -> str:
    if telegram_bot_id <= 0:
        raise ValueError("telegram_bot_id must be positive")
    token = _call(
        _require_admin_token(admin_token),
        "getManagedBotToken",
        user_id=telegram_bot_id,
    )
    if not isinstance(token, str) or not token:
        raise RuntimeError("Telegram API returned an invalid managed bot token")
    return token


def configure_managed_bot_webhook(
    bot_token: str,
    telegram_bot_id: int,
    *,
    child_webhook_url: str | None,
    webhook_secret_token: str | None,
) -> None:
    if not bot_token:
        raise ValueError("bot_token is required")
    if telegram_bot_id <= 0:
        raise ValueError("telegram_bot_id must be positive")
    if not child_webhook_url:
        raise RuntimeError("ADMIN_BOT_CHILD_WEBHOOK_URL is required")
    if not webhook_secret_token:
        raise RuntimeError("WEBHOOK_SECRET_TOKEN is required")

    _call(
        bot_token,
        "setWebhook",
        url=(f"{child_webhook_url.rstrip('/')}" f"/{telegram_bot_id}"),
        secret_token=managed_bot_webhook_secret(
            webhook_secret_token,
            telegram_bot_id,
        ),
        allowed_updates=["message"],
    )


def configure_managed_bot_commands(bot_token: str) -> None:
    if not bot_token:
        raise ValueError("bot_token is required")
    _call(
        bot_token,
        "setMyCommands",
        commands=[
            {"command": "balance", "description": "Show remaining limit"},
            {"command": "transactions", "description": "Show recent transactions"},
        ],
    )


class ManagedBotTelegramApi:
    """Telegram calls used by the managed-bot activation lifecycle."""

    def __init__(
        self,
        *,
        admin_token: str | None,
        child_webhook_url: str | None,
        webhook_secret_token: str | None,
    ) -> None:
        self.admin_token = admin_token
        self.child_webhook_url = child_webhook_url
        self.webhook_secret_token = webhook_secret_token

    def get_managed_bot_token(self, telegram_bot_id: int) -> str:
        return get_managed_bot_token(telegram_bot_id, admin_token=self.admin_token)

    def configure_child_webhook(
        self, child_bot_token: str, telegram_bot_id: int
    ) -> None:
        configure_managed_bot_webhook(
            child_bot_token,
            telegram_bot_id,
            child_webhook_url=self.child_webhook_url,
            webhook_secret_token=self.webhook_secret_token,
        )

    def configure_child_commands(self, child_bot_token: str) -> None:
        configure_managed_bot_commands(child_bot_token)

    def set_access_open(self, telegram_bot_id: int) -> None:
        _call(
            _require_admin_token(self.admin_token),
            "setManagedBotAccessSettings",
            user_id=telegram_bot_id,
            is_access_restricted=False,
        )

    def restrict_access(self, telegram_bot_id: int, recipient_id: int) -> None:
        _call(
            _require_admin_token(self.admin_token),
            "setManagedBotAccessSettings",
            user_id=telegram_bot_id,
            is_access_restricted=True,
            added_user_ids=[recipient_id],
        )

    def get_access_settings(self, telegram_bot_id: int) -> dict[str, Any]:
        result = _call(
            _require_admin_token(self.admin_token),
            "getManagedBotAccessSettings",
            user_id=telegram_bot_id,
        )
        if not isinstance(result, dict):
            raise RuntimeError("Telegram API returned invalid access settings")
        return result


def _require_admin_token(token: str | None) -> str:
    if not token:
        raise RuntimeError("ADMIN_BOT_TOKEN is required")
    return token


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
