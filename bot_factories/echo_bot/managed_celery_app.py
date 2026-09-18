"""One echo worker for all bots created by the private manager."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import Update

from bot_factories.admin_bot.config import admin_settings
from bot_factories.admin_bot.telegram_api import telegram_call
from bot_factories.echo_bot.telegram_routes import echo_router
from shared.bot_registry import BotRegistry, MANAGED_ECHO_QUEUE, MANAGED_ECHO_TASK
from worker.celery_factory import CeleryFactory

celery_app = CeleryFactory.create_app()
celery_app.conf.task_default_queue = MANAGED_ECHO_QUEUE
dispatcher = Dispatcher()
dispatcher.include_router(echo_router)


async def dispatch(bot_id, body):
    record = BotRegistry().get(bot_id)
    if not record or record["status"] != "active" or record["kind"] != "echo":
        return
    if record["owner_id"] != admin_settings.owner_id:
        return
    token = await telegram_call(
        admin_settings.token, "getManagedBotToken", user_id=bot_id
    )
    async with Bot(token=token) as bot:
        if bot.id != bot_id:
            raise ValueError("Managed bot identity mismatch")
        await dispatcher.feed_update(bot, Update.model_validate(body))


@celery_app.task(name=MANAGED_ECHO_TASK)
def process_telegram_update(bot_id, body):
    asyncio.run(dispatch(bot_id, body))
