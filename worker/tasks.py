import asyncio
import json
import logging

import httpx
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


@celery_app.task
def process_face_swap_task(photo_path: str, video_path: str) -> dict:
    url = "https://example.com/api/generate"

    payload = {
        "photo_path": photo_path,
        "video_path": video_path,
    }

    logger.info(
        f"Sending generation request: {json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, json=payload)

        response.raise_for_status()

        logger.info(f"Success response: {response.text}")
        return response.json()

    except httpx.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        return {"error": str(e), "success": False}
