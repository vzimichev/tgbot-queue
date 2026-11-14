import asyncio
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from celery import shared_task

from shared.managed_bots.repositories.bot_manager import ManagedBotsRepository
from bot_factories.managed_bot.routes import managed_bot_router


MANAGED_BOT_UPDATES_TASK = "managed_bot.updates"

managed_bot_dispatcher = Dispatcher()
managed_bot_dispatcher.include_router(managed_bot_router)


def managed_bot_token(bot_id: int) -> str | None:
    bot = ManagedBotsRepository().get_by_telegram_bot_id(bot_id)
    return bot.child_bot_token if bot else None


async def dispatch_managed_update(bot_id: int, body: dict[str, Any]) -> dict[str, str]:
    """Dispatch one managed ingress update using the token for its bot ID."""
    update_id = body.get("update_id")
    if not isinstance(update_id, int):
        raise ValueError("Managed update must contain an integer update_id")

    token = await asyncio.to_thread(managed_bot_token, bot_id)
    if not token:
        return {"status": "ignored"}

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


@shared_task(name=MANAGED_BOT_UPDATES_TASK)
def managed_bot_updates(bot_id: int, body: dict[str, Any]) -> dict[str, str]:
    return asyncio.run(dispatch_managed_update(bot_id, body))
