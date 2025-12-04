import json
import logging
from pathlib import Path

from pydantic import ValidationError

from shared.config import settings
from worker.celery_app import celery_app
from worker.models.telegram import Update
from worker.services.telegram import TelegramClient

logger = logging.getLogger("worker")
telegram = TelegramClient(settings.telegram_token)
cache_folder = Path(__file__).parent / ".cache"


@celery_app.task
def process_telegram_task(body: dict) -> None:
    logger.info("Received task: %s", json.dumps(body, ensure_ascii=False))

    try:
        update = Update(**body)
    except ValidationError as e:
        logger.error(e)
        return

    msg = update.message
    chat_id = msg.chat.id
    tmp_folder = f"{msg.date}-{msg.media_group_id}"

    file_paths = telegram.download_all_files(
        message=msg, dest_dir=f"{cache_folder}/{tmp_folder}"
    )
    telegram.send_message(
        chat_id=chat_id, text=f"{len(file_paths)} file(s) downloaded."
    )
