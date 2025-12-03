import json
import logging

from services.telegram import send_message
from worker.celery_app import celery_app

logger = logging.getLogger("worker")


@celery_app.task(bind=True, name="process_telegram_task")
def process_telegram_task(self, message: dict):
    logger.info("Received task: %s", json.dumps(message, ensure_ascii=False))

    text = message.get("message", {}).get("text", "<no text>")
    response = f"Rabbit answered: {text}"

    send_message(chat_id=message.get("chat_id"), text=response)

    logger.info("Task processed with response: %s", response)
    return response
