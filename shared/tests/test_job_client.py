import asyncio
import unittest
from unittest.mock import patch

from shared.job_client import HttpJobClient


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class FakeAsyncClient:
    post_url: str | None = None
    status_url: str | None = None
    payload: dict | None = None

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url: str, json: dict) -> FakeResponse:
        type(self).post_url = url
        type(self).payload = json
        await asyncio.sleep(0.01)
        return FakeResponse({"status": "done", "job_id": json["job_id"]})

    async def get(self, url: str, timeout: float) -> FakeResponse:
        type(self).status_url = url
        return FakeResponse({"status": "running", "stage": "work", "percent": 42})


class HttpJobClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_runs_and_polls_the_reusable_job_protocol(self):
        updates = []

        async def collect(status: dict) -> None:
            updates.append(status)

        client = HttpJobClient("http://worker:8001/", poll_interval=0.001)
        with patch("shared.job_client.httpx.AsyncClient", FakeAsyncClient):
            result = await client.run({"input": "value"}, collect)

        job_id = FakeAsyncClient.payload["job_id"]
        self.assertEqual(FakeAsyncClient.post_url, "http://worker:8001/run")
        self.assertEqual(
            FakeAsyncClient.status_url,
            f"http://worker:8001/jobs/{job_id}/status",
        )
        self.assertEqual(FakeAsyncClient.payload["input"], "value")
        self.assertEqual(result["status"], "done")
        self.assertTrue(any(update.get("percent") == 42 for update in updates))
        self.assertEqual(updates[-1]["percent"], 100)


if __name__ == "__main__":
    unittest.main()
