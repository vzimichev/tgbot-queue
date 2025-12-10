import asyncio
import json
import logging

from aiogram.types import Update

logger = logging.getLogger(__name__)


def create_process_telegram_task(celery_app, dp):
    @celery_app.task(bind=True)
    def process_telegram_task(self, body: dict) -> None:
        logger.info("Received task: %s", json.dumps(body, ensure_ascii=False))
        update = Update(**body)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(dp.feed_update(update=update, bot=dp.bot))
        return "lol"

    return process_telegram_task
