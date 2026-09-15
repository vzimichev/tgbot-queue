import json
import logging
from pathlib import Path
from uuid import uuid4

from aiogram import Bot

from bot_factories.faceswap_bot.config import faceswap_settings
from shared.job_client import HttpJobClient, ProgressCallback

logger = logging.getLogger(__name__)


cache_folder = Path(__file__).parent / ".cache"


async def process_face_fusion_task(
    photo_path: Path,
    video_path: Path,
    progress_callback: ProgressCallback | None = None,
    poll_interval: float = 2.0,
) -> Path:
    output_path = video_path.parent / f"result-{uuid4().hex}.mp4"
    payload = {
        "source_paths": [str(photo_path.resolve())],
        "target_path": str(video_path.resolve()),
        "output_path": str(output_path.resolve()),
    }

    logger.info(
        f"Sending generation request: {json.dumps(payload, ensure_ascii=False)}"
    )

    client = HttpJobClient(
        base_url=faceswap_settings.api_base_url,
        poll_interval=poll_interval,
    )
    response = await client.run(payload, progress_callback=progress_callback)
    logger.info("Success response: %s", response)
    if not output_path.is_file():
        raise RuntimeError(f"FaceFusion did not create {output_path}")
    return output_path


async def save_document(bot: Bot, file_id: str, file_name: str) -> Path:
    folder = cache_folder / str(bot.id)
    folder.mkdir(parents=True, exist_ok=True)

    file = await bot.get_file(file_id)
    path = folder / str(file_name)
    await bot.download_file(file.file_path, destination=path)
    return path
