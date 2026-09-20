from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from shared.config import settings
from worker.celery_factory import TELEGRAM_UPDATE_QUEUE, TELEGRAM_UPDATE_TASK


def test_webhook_publishes_raw_update_to_shared_queue():
    update = {"update_id": 42, "message": {"text": "hello"}}

    with patch.object(settings, "webhook_secret_token", None), patch(
        "api.telegram_webhook.celery_app.send_task"
    ) as send_task:
        response = TestClient(app).post("/webhook", json=update)

    assert response.status_code == 200
    send_task.assert_called_once_with(
        TELEGRAM_UPDATE_TASK,
        args=[update],
        queue=TELEGRAM_UPDATE_QUEUE,
    )
