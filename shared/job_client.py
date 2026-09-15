import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

JobStatus = dict[str, Any]
ProgressCallback = Callable[[JobStatus], Awaitable[None]]


class HttpJobClient:
    """Client for the queue worker's HTTP job-progress protocol."""

    def __init__(self, base_url: str, poll_interval: float = 2.0):
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval

    async def run(
        self,
        payload: dict[str, Any],
        progress_callback: ProgressCallback | None = None,
    ) -> JobStatus:
        job_id = uuid4().hex
        request_payload = {**payload, "job_id": job_id}
        timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            request_task = asyncio.create_task(
                client.post(f"{self.base_url}/run", json=request_payload)
            )
            while not request_task.done():
                await asyncio.sleep(self.poll_interval)
                try:
                    status_response = await client.get(
                        f"{self.base_url}/jobs/{job_id}/status",
                        timeout=10.0,
                    )
                    if status_response.status_code == 200 and progress_callback:
                        await progress_callback(status_response.json())
                except httpx.HTTPError as exc:
                    logger.warning("Could not fetch job progress: %s", exc)

            response = await request_task

        response.raise_for_status()
        result = response.json()
        if progress_callback:
            await progress_callback(
                {
                    "job_id": job_id,
                    "status": "done",
                    "stage": "complete",
                    "percent": 100,
                }
            )
        return result
