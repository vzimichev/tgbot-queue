import asyncio
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from celery import shared_task

from bot_factories.admin_bot.repositories.managed_bots import ManagedBotsRepository
from bot_factories.admin_bot.telegram_routes import managed_bot_router


MANAGED_BOT_UPDATES_TASK = "managed_bot.updates"

managed_bot_dispatcher = Dispatcher()
managed_bot_dispatcher.include_router(managed_bot_router)


def managed_bot_token(bot_id: int) -> str | None:
    bot = ManagedBotsRepository().get_by_telegram_bot_id(bot_id)
    return bot.child_bot_token if bot else None


@shared_task(name=MANAGED_BOT_UPDATES_TASK)
def managed_bot_updates(bot_id: int, body: dict[str, Any]) -> dict[str, str]:
    token = managed_bot_token(bot_id)
    update_id = body.get("update_id")
    if not token or not isinstance(update_id, int):
        return {"status": "ignored"}

    async def dispatch() -> dict[str, str]:
        bot = Bot(token=token)
        try:
            return await managed_bot_dispatcher.feed_update(
                bot=bot,
                update=Update.model_validate(body),
                managed_bot_id=bot_id,
                managed_update_id=update_id,
            )
        finally:
            await bot.session.close()

    return asyncio.run(dispatch())
