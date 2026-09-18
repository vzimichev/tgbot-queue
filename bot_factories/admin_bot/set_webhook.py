"""Register the admin bot with the existing HTTPS gateway."""

from urllib.parse import urlsplit

from bot_factories.admin_bot.config import admin_settings
from bot_factories.admin_bot.telegram import TelegramAPI
from shared.config import settings


def main():
    url = admin_settings.public_base_url.rstrip("/") + "/webhook"
    parsed = urlsplit(url)
    secret = admin_settings.webhook_secret.get_secret_value()
    if parsed.scheme != "https" or not parsed.hostname or not secret:
        raise SystemExit(
            "ADMIN_BOT_PUBLIC_BASE_URL must be HTTPS and webhook secret must be set"
        )
    if secret == settings.webhook_secret_token:
        raise SystemExit("Admin and primary bot webhook secrets must differ")
    api = TelegramAPI(admin_settings.token.get_secret_value())
    api.call(
        "setWebhook",
        url=url,
        secret_token=secret,
        allowed_updates=["message", "managed_bot"],
        max_connections=1,
        drop_pending_updates=False,
    )
    if api.call("getWebhookInfo").get("url") != url:
        raise SystemExit("Telegram did not confirm the admin webhook URL")
    print(f"Admin bot webhook is set to {url}")


if __name__ == "__main__":
    main()
