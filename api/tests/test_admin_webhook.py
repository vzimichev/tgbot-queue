import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.telegram_webhook import webhook_router

app = FastAPI()
app.include_router(webhook_router)


def test_shared_webhook_routes_by_secret_and_deduplicates_admin_updates():
    admin_settings = SimpleNamespace(
        token=SecretStr("test-token"),
        webhook_secret=SecretStr("admin-secret"),
        owner_id=123,
    )
    primary_settings = SimpleNamespace(
        webhook_secret_token="primary-secret",
        telegram_task_name="echo_bot.process_telegram_update",
        telegram_queue="echo_bot",
    )
    celery_module = ModuleType("worker.celery_app")
    celery_module.celery_app = Mock()
    update = {"update_id": 17, "message": {"from": {"id": 123}}}
    with tempfile.TemporaryDirectory() as folder:
        with (
            patch("api.admin_webhook.admin_settings", admin_settings),
            patch("api.telegram_webhook.admin_settings", admin_settings),
            patch("api.telegram_webhook.settings", primary_settings),
            patch.dict("os.environ", {"ADMIN_BOT_DATA_DIR": folder}),
            patch.dict(sys.modules, {"worker.celery_app": celery_module}),
            patch("api.admin_webhook.TelegramAPI"),
            patch("api.admin_webhook.AdminService") as service,
        ):
            client = TestClient(app)
            assert client.post("/webhook", json=update).status_code == 403
            admin_headers = {"X-Telegram-Bot-Api-Secret-Token": "admin-secret"}
            assert (
                client.post("/webhook", json=update, headers=admin_headers).status_code
                == 200
            )
            assert (
                client.post("/webhook", json=update, headers=admin_headers).status_code
                == 200
            )
            service.return_value.handle.assert_called_once_with(update)
            celery_module.celery_app.send_task.assert_not_called()

            primary_headers = {"X-Telegram-Bot-Api-Secret-Token": "primary-secret"}
            assert (
                client.post(
                    "/webhook", json=update, headers=primary_headers
                ).status_code
                == 200
            )
            celery_module.celery_app.send_task.assert_called_once_with(
                "echo_bot.process_telegram_update", args=[update], queue="echo_bot"
            )
