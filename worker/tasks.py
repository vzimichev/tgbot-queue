import asyncio
import json
import logging

from aiogram.types import Update

from worker.main import celery_app
from worker.telegram.bot import bot
from worker.telegram.dispatcher import dp

logger = logging.getLogger("worker")


@celery_app.task
def process_telegram_task(body: dict) -> None:
    logger.info("Received task: %s", json.dumps(body, ensure_ascii=False))
    update = Update(**body)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(dp.feed_update(bot=bot, update=update))


