import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot_factories.faceswap_bot.repository import _status_url, process_face_fusion_task


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class FakeAsyncClient:
    last_payload: dict | None = None

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url: str, json: dict) -> FakeResponse:
        type(self).last_payload = json
        await asyncio.sleep(0.01)
        Path(json["output_path"]).write_bytes(b"video")
        return FakeResponse({"status": "done", "job_id": json["job_id"]})

    async def get(self, url: str, timeout: float) -> FakeResponse:
        return FakeResponse({"status": "running", "stage": "processing", "percent": 42})


class FaceSwapProgressTest(unittest.IsolatedAsyncioTestCase):
    def test_status_url_replaces_run_endpoint(self):
        self.assertEqual(
            _status_url("http://127.0.0.1:8001/run", "abc"),
            "http://127.0.0.1:8001/jobs/abc/status",
        )

    async def test_processing_polls_progress_until_result_is_ready(self):
        updates = []

        async def collect(status: dict) -> None:
            updates.append(status)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photo = root / "source.jpg"
            video = root / "target.mp4"
            photo.write_bytes(b"photo")
            video.write_bytes(b"video")

            with patch(
                "bot_factories.faceswap_bot.repository.httpx.AsyncClient",
                FakeAsyncClient,
            ):
                output = await process_face_fusion_task(
                    photo,
                    video,
                    progress_callback=collect,
                    poll_interval=0.001,
                )

            self.assertEqual(output.read_bytes(), b"video")

        self.assertTrue(any(update.get("percent") == 42 for update in updates))
        self.assertEqual(updates[-1]["percent"], 100)
        self.assertIsNotNone(FakeAsyncClient.last_payload["job_id"])


if __name__ == "__main__":
    unittest.main()
