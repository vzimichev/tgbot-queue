import asyncio
import json
import logging

from aiogram.types import Update

from bot_factories.echo_bot import celery_app
from worker.telegram_client import bot, dp

logger = logging.getLogger("echo_bot")


@celery_app.task
def process_telegram_task(body: dict) -> None:
    logger.info("Received task: %s", json.dumps(body, ensure_ascii=False))
    update = Update(**body)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(dp.feed_update(bot=bot, update=update))


@celery_app.task
def process_echo_task(message: str):
    logger.info(f"Echo task received message: {message}")
    return {"echo": message, "success": True}
