"""Run once to register the manager webhook, after enabling Managed Bots."""

import asyncio

from bot_factories.admin_bot.config import admin_settings
from bot_factories.admin_bot.telegram_api import telegram_call


async def setup():
    admin_settings.validate_runtime()
    identity = await telegram_call(admin_settings.token, "getMe")
    if not identity.get("can_manage_bots"):
        raise RuntimeError("Enable bot management in the BotFather Mini App first")
    await telegram_call(
        admin_settings.token,
        "setWebhook",
        url=f"{admin_settings.public_base_url.rstrip('/')}/webhook/admin",
        secret_token=admin_settings.webhook_secret,
        allowed_updates=["message", "managed_bot"],
    )
    print("Admin bot webhook configured.")


if __name__ == "__main__":
    asyncio.run(setup())
