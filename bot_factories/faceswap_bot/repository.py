import json
import logging
from pathlib import Path

import httpx
from aiogram import Bot

logger = logging.getLogger(__name__)


cache_folder = Path(__file__).parent / ".cache"


async def process_face_fusion_task(photo_path: Path, video_path: Path) -> dict:
    url = "http://api/generate"

    # Convert Path objects to strings
    payload = {
        "photo_path": str(photo_path),
        "video_path": str(video_path),
    }

    logger.info(f"Sending generation request: {json.dumps(payload, ensure_ascii=False)}")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload)

        response.raise_for_status()

        logger.info(f"Success response: {response.text}")
        return response.json()

    except httpx.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        return {"error": str(e), "success": False}



async def save_document(bot: Bot, file_id: str, file_name: str) -> Path:
    file = await bot.get_file(file_id)
    path = cache_folder / file_name
    await bot.download_file(file.file_path, destination=path)
    return path
