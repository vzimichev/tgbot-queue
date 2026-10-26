import json
import logging
from pathlib import Path
from uuid import uuid4

from aiogram import Bot

from bot_factories.admin_bot.config import admin_bot_settings
from shared.job_client import HttpJobClient, ProgressCallback

logger = logging.getLogger(__name__)

cache_folder = Path(__file__).parent / ".cache" / "faceswap"


async def save_media(bot: Bot, file_id: str, file_name: str) -> Path:
    """Download an input file into the managed bot's private cache."""
    folder = cache_folder / str(bot.id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid4().hex}-{Path(file_name).name}"
    telegram_file = await bot.get_file(file_id)
    await bot.download_file(telegram_file.file_path, destination=path)
    return path


async def process_faceswap_task(
    photo_path: Path,
    video_path: Path,
    progress_callback: ProgressCallback | None = None,
    poll_interval: float = 2.0,
) -> Path:
    """Submit a FaceFusion job to the same HTTP queue used by Faceswapbot."""
    output_path = video_path.parent / f"result-{uuid4().hex}.mp4"
    payload = {
        "source_paths": [str(photo_path.resolve())],
        "target_path": str(video_path.resolve()),
        "output_path": str(output_path.resolve()),
    }
    logger.info("Sending managed FaceSwap request: %s", json.dumps(payload))
    await HttpJobClient(
        base_url=admin_bot_settings.faceswap_api_base_url,
        poll_interval=poll_interval,
    ).run(payload, progress_callback=progress_callback)
    if not output_path.is_file():
        raise RuntimeError(f"FaceFusion did not create {output_path}")
    return output_path
