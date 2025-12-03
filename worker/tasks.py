import json
import logging

from services.telegram import send_message
from worker.celery_app import celery_app

logger = logging.getLogger("worker")


@celery_app.task
def process_telegram_task(body: dict):
    logger.info("Received task: %s", json.dumps(body, ensure_ascii=False))

    message = body.get("message", {})
    text = message.get("text", "<no text>")
    chat_id = message.get("chat", {}).get("id")

    response = f"Rabbit answered: {text}"

    send_message(chat_id=chat_id, text=response)

    logger.info("Task processed with response: %s", response)
    return response
