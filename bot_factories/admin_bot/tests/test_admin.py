import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app
from bot_factories.admin_bot.service import AdminService
from bot_factories.admin_bot.config import AdminSettings
from shared.bot_registry import BotRegistry


class MemoryRegistry:
    def __init__(self):
        self.records = {}

    def get(self, bot_id):
        return self.records.get(bot_id, {}).copy() or None

    def save(self, record):
        self.records[record["id"]] = record.copy()

    def list(self):
        return list(self.records.values())


class AdminTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = MemoryRegistry()
        self.config = SimpleNamespace(
            token="manager", owner_id=7, public_base_url="https://example.com"
        )
        self.call = AsyncMock()
        self.service = AdminService(self.registry, self.call, self.config)

    async def test_private_owner_only(self):
        for user_id, chat_type in [(8, "private"), (7, "group")]:
            await self.service.handle(
                {
                    "message": {
                        "from": {"id": user_id},
                        "chat": {"type": chat_type},
                        "text": "/start",
                    }
                }
            )
        self.call.assert_not_awaited()
        await self.service.handle(
            {
                "message": {
                    "from": {"id": 7},
                    "chat": {"type": "private"},
                    "text": "/start",
                }
            }
        )
        self.assertIn(
            "request_managed_bot",
            self.call.call_args.kwargs["reply_markup"]["keyboard"][0][0],
        )

    async def test_connect_and_duplicate_preserve_secret(self):
        self.call.side_effect = ["child-token", {"id": 123}, True, True] * 2
        update = {
            "managed_bot": {
                "user": {"id": 7},
                "bot": {"id": 123, "username": "sample_bot"},
            }
        }
        await self.service.handle(update)
        secret = self.registry.get(123)["secret"]
        await self.service.handle(update)
        self.assertEqual(len(self.registry.list()), 1)
        self.assertEqual(self.registry.get(123)["secret"], secret)
        self.assertEqual(self.registry.get(123)["status"], "active")
        self.assertNotIn("child-token", str(self.registry.list()))
        self.assertEqual(
            self.call.call_args_list[2].kwargs["url"],
            "https://example.com/webhook/managed/123",
        )

    async def test_failed_setup_can_retry(self):
        self.call.side_effect = [RuntimeError("failure"), True]
        await self.service.connect({"id": 123, "username": "sample_bot"})
        self.assertEqual(self.registry.get(123)["status"], "error")
        self.call.side_effect = ["child-token", {"id": 123}, True, True]
        await self.service.handle(
            {
                "message": {
                    "from": {"id": 7},
                    "chat": {"type": "private"},
                    "text": "/retry 123",
                }
            }
        )
        self.assertEqual(self.registry.get(123)["status"], "active")

    async def test_foreign_creation_and_transfer(self):
        update = {"managed_bot": {"user": {"id": 8}, "bot": {"id": 123}}}
        await self.service.handle(update)
        self.call.assert_not_awaited()
        self.assertIsNone(self.registry.get(123))
        self.registry.save({"id": 123, "status": "active"})
        await self.service.handle(update)
        self.assertEqual(self.registry.get(123)["status"], "disabled")


class GatewayTest(unittest.TestCase):
    def test_managed_routes_require_correct_secret(self):
        with patch("api.telegram_webhook.BotRegistry") as registry, patch(
            "api.telegram_webhook.celery_app.send_task"
        ) as send:
            registry.return_value.get.return_value = {
                "kind": "echo",
                "status": "active",
                "secret": "valid",
            }
            with TestClient(app) as client:
                for secret in ["", "bad"]:
                    result = client.post(
                        "/webhook/managed/123",
                        json={"update_id": 1},
                        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
                    )
                    self.assertEqual(result.status_code, 403)
                send.assert_not_called()
                result = client.post(
                    "/webhook/managed/123",
                    json={"update_id": 1},
                    headers={"X-Telegram-Bot-Api-Secret-Token": "valid"},
                )
                self.assertEqual(result.status_code, 200)
                send.assert_called_once_with(
                    "managed_echo.process_telegram_update",
                    args=[123, {"update_id": 1}],
                    queue="managed_echo",
                )
                registry.return_value.get.return_value = None
                self.assertEqual(
                    client.post("/webhook/managed/456", json={}).status_code, 404
                )

    def test_admin_fails_closed_without_secret(self):
        with patch(
            "api.telegram_webhook.admin_settings", SimpleNamespace(webhook_secret="")
        ), patch("api.telegram_webhook.celery_app.send_task") as send:
            with TestClient(app) as client:
                self.assertEqual(
                    client.post("/webhook/admin", json={}).status_code, 403
                )
            send.assert_not_called()

    def test_registry_survives_new_instance(self):
        client = MagicMock()
        values = {}
        client.hset.side_effect = lambda key, field, value: values.update(
            {field: value}
        )
        client.hget.side_effect = lambda key, field: values.get(field)
        BotRegistry(client).save({"id": 1, "status": "active"})
        self.assertEqual(BotRegistry(client).get(1)["status"], "active")

    def test_placeholder_cannot_start(self):
        with self.assertRaises(ValueError):
            AdminSettings(_env_file=None).validate_runtime()


class EchoTest(unittest.IsolatedAsyncioTestCase):
    async def test_two_bots_reply_with_their_own_tokens(self):
        from bot_factories.echo_bot import managed_celery_app as runtime
        from aiogram import Bot

        replies = []

        async def capture(bot, method, **kwargs):
            replies.append((bot.id, method.text, method.parse_mode))
            return True

        with patch.object(runtime, "BotRegistry") as registry, patch.object(
            runtime, "admin_settings", SimpleNamespace(token="manager", owner_id=7)
        ), patch.object(
            runtime, "telegram_call", AsyncMock(side_effect=["123:ABC", "456:DEF"])
        ), patch.object(
            Bot, "__call__", capture
        ):
            registry.return_value.get.return_value = {
                "status": "active",
                "kind": "echo",
                "owner_id": 7,
            }
            for bot_id in [123, 456]:
                await runtime.dispatch(
                    bot_id,
                    {
                        "update_id": bot_id,
                        "message": {
                            "message_id": 1,
                            "date": 1,
                            "chat": {"id": 7, "type": "private"},
                            "from": {"id": 7, "is_bot": False, "first_name": "Owner"},
                            "text": "*literal_ text",
                        },
                    },
                )
        self.assertEqual(
            replies, [(123, "*literal_ text", None), (456, "*literal_ text", None)]
        )
