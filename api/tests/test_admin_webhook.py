import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.admin_webhook import admin_webhook_router

app = FastAPI()
app.include_router(admin_webhook_router)


def test_admin_webhook_checks_secret_and_deduplicates_updates():
    settings = SimpleNamespace(
        token=SecretStr("test-token"),
        webhook_secret=SecretStr("test-secret"),
        owner_id=123,
    )
    update = {"update_id": 17, "message": {"from": {"id": 123}}}
    with tempfile.TemporaryDirectory() as folder:
        with (
            patch("api.admin_webhook.admin_settings", settings),
            patch.dict("os.environ", {"ADMIN_BOT_DATA_DIR": folder}),
            patch("api.admin_webhook.TelegramAPI"),
            patch("api.admin_webhook.AdminService") as service,
        ):
            client = TestClient(app)
            assert client.post("/admin/webhook", json=update).status_code == 403
            headers = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}
            assert client.post(
                "/admin/webhook", json=update, headers=headers
            ).json() == {"ok": True}
            assert client.post(
                "/admin/webhook", json=update, headers=headers
            ).json() == {"ok": True}
            service.return_value.handle.assert_called_once_with(update)
