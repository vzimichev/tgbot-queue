import json
import logging
from pathlib import Path
from uuid import uuid4

import httpx
from aiogram import Bot

from bot_factories.faceswap_bot.config import faceswap_settings

logger = logging.getLogger(__name__)


cache_folder = Path(__file__).parent / ".cache"


async def process_face_fusion_task(photo_path: Path, video_path: Path) -> Path:
    output_path = video_path.parent / f"result-{uuid4().hex}.mp4"
    payload = {
        "source_paths": [str(photo_path.resolve())],
        "target_path": str(video_path.resolve()),
        "output_path": str(output_path.resolve()),
    }

    logger.info(
        f"Sending generation request: {json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(faceswap_settings.api_url, json=payload)

        response.raise_for_status()

        logger.info(f"Success response: {response.text}")
        if not output_path.is_file():
            raise RuntimeError(f"FaceFusion did not create {output_path}")
        return output_path

    except httpx.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        raise RuntimeError(f"FaceFusion request failed: {e}") from e


async def save_document(bot: Bot, file_id: str, file_name: str) -> Path:
    folder = cache_folder / str(bot.id)
    folder.mkdir(parents=True, exist_ok=True)

    file = await bot.get_file(file_id)
    path = folder / str(file_name)
    await bot.download_file(file.file_path, destination=path)
    return path
