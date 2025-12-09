import json

import httpx

from worker.main import celery_app
from worker.tasks import logger


@celery_app.task
def process_face_fusion_task(photo_path: str, video_path: str) -> dict:
    url = f"http://api/generate"

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
