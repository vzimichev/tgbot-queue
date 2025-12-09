import logging

import httpx
from aiogram import Dispatcher

from bot_factories.faceswap_bot.tgbot_routes import face_swap_router
from worker.celery_app import celery_app

logger = logging.getLogger("faceswap_factory")


def get_facefusion_task(url: str):
    @celery_app.task(name="process_face_fusion_task")
    def task(photo_path: str, video_path: str) -> dict:
        payload = {"photo_path": photo_path, "video_path": video_path}
        logger.info(f"Sending generation request: {payload}")
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Success response: {response.text}")
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            return {"error": str(e), "success": False}

    return task


def get_dispatcher():
    dp = Dispatcher()
    dp.include_router(face_swap_router)
    return dp
