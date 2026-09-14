import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import uuid4

import httpx
from aiogram import Bot

from bot_factories.faceswap_bot.config import faceswap_settings

logger = logging.getLogger(__name__)


cache_folder = Path(__file__).parent / ".cache"


ProgressCallback = Callable[[dict], Awaitable[None]]


def _status_url(api_url: str, job_id: str) -> str:
    run_url = api_url.rstrip("/")
    base_url = run_url[:-4] if run_url.endswith("/run") else run_url
    return f"{base_url}/jobs/{job_id}/status"


async def process_face_fusion_task(
    photo_path: Path,
    video_path: Path,
    progress_callback: ProgressCallback | None = None,
    poll_interval: float = 2.0,
) -> Path:
    job_id = uuid4().hex
    output_path = video_path.parent / f"result-{uuid4().hex}.mp4"
    payload = {
        "job_id": job_id,
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
            request_task = asyncio.create_task(
                client.post(faceswap_settings.api_url, json=payload)
            )
            while not request_task.done():
                await asyncio.sleep(poll_interval)
                try:
                    status_response = await client.get(
                        _status_url(faceswap_settings.api_url, job_id),
                        timeout=10.0,
                    )
                    if status_response.status_code == 200 and progress_callback:
                        await progress_callback(status_response.json())
                except httpx.HTTPError as exc:
                    logger.warning("Could not fetch FaceFusion progress: %s", exc)
            response = await request_task

        response.raise_for_status()

        logger.info(f"Success response: {response.text}")
        if not output_path.is_file():
            raise RuntimeError(f"FaceFusion did not create {output_path}")
        if progress_callback:
            await progress_callback(
                {"status": "done", "stage": "complete", "percent": 100}
            )
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
