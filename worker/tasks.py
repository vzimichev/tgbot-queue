import json
import logging

from worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def process_telegram_task(body: dict) -> None:
    logger.info("Received task: %s", json.dumps(body, ensure_ascii=False))
