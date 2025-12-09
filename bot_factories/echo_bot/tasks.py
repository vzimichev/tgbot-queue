import logging

from bot_factories.echo_bot.celery_app import celery_app

logger = logging.getLogger("echo_bot")


@celery_app.task
def process_echo_task(message: str):
    logger.info(f"Echo task received message: {message}")
    return {"echo": message, "success": True}
