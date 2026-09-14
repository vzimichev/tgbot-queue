import asyncio
import json
import logging

from aiogram.types import Update

logger = logging.getLogger(__name__)


def register_default_telegram_task(celery_app, *, task_name: str):

    @celery_app.task(name=task_name)
    def process_telegram_task(body: dict):
        logger.info("Received task: %s", json.dumps(body, ensure_ascii=False))

        update = Update(**body)

        dp = celery_app.dp
        bot = celery_app.bot

        loop = getattr(celery_app, "telegram_event_loop", None)
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            celery_app.telegram_event_loop = loop
        try:
            loop.run_until_complete(dp.feed_update(bot=bot, update=update))
        except Exception as error:
            logger.exception(
                "Telegram update failed: error=%r cause=%r context=%r",
                error,
                error.__cause__,
                error.__context__,
            )
            raise

        return {"status": "ok"}

    return process_telegram_task
