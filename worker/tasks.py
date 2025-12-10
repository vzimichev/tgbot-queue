import asyncio
import json
import logging

from aiogram.types import Update

logger = logging.getLogger(__name__)


def register_default_telegram_task(celery_app):

    @celery_app.task(name="process_telegram_task")
    def process_telegram_task(body: dict):
        logger.info("Received task: %s", json.dumps(body, ensure_ascii=False))

        update = Update(**body)

        dp = celery_app.dp

        loop = asyncio.get_event_loop()
        loop.run_until_complete(dp.feed_update(bot=dp.bot, update=update))

        return {"status": "ok"}

    return process_telegram_task
