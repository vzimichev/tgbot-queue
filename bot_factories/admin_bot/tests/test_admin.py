import unittest
from unittest.mock import Mock, patch


from bot_factories.admin_bot.telegram_routes import AdminService, notify_child_claim


class MemoryRepository:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)

    def list_bots(self):
        return [v for k, v in self.data.items() if k.startswith("bot:")]

    def list_pending(self):
        return [v for k, v in self.data.items() if k.startswith("pending:")]


class AdminTest(unittest.TestCase):
    def setUp(self):
        self.repo = MemoryRepository()
        self.api = Mock()
        self.api.call.side_effect = lambda method, **kw: {
            "getMe": {"username": "manager_bot"},
            "getManagedBotToken": "secret-token",
            "getManagedBotAccessSettings": {
                "is_access_restricted": True,
                "added_users": [{"id": 456}],
            },
        }.get(method, True)
        self.service = AdminService(self.api, self.repo, 123)

    def claim_from_child(self, record, message, child_api):
        result = self.service.bots.claim_from_message(record, message)
        notify_child_claim(message, child_api, result)
        return result == "configured"

    def message(self, text, user=123, chat=123):
        self.service.handle(
            {"message": {"from": {"id": user}, "chat": {"id": chat}, "text": text}}
        )

    def select_user(self, username="some_user", request_id=None):
        self.service.handle(
            {
                "message": {
                    "from": {"id": 123},
                    "chat": {"id": 123},
                    "users_shared": {
                        "request_id": (
                            request_id
                            if request_id is not None
                            else self.repo.get("draft")["request_id"]
                        ),
                        "users": [
                            {
                                "user_id": 456,
                                "username": username,
                                "first_name": "Alice",
                            }
                        ],
                    },
                }
            }
        )

    def test_denies_other_users_and_groups(self):
        self.message("/create", user=456)
        self.message("/create", chat=-456)
        self.api.call.assert_not_called()
        self.assertEqual(self.repo.data, {})

    def test_creation_persists_parameters_without_child_calls(self):
        self.message("/create")
        self.select_user()
        self.message("600")
        pending_key = next(k for k in self.repo.data if k.startswith("pending:"))
        username = pending_key.split(":", 1)[1]
        creation = self.api.call.call_args.kwargs
        request = creation["reply_markup"]["keyboard"][0][0]["request_managed_bot"]
        self.assertEqual(request["suggested_username"], username)
        self.assertEqual(request["suggested_name"], self.repo.get(pending_key)["name"])
        event = {
            "managed_bot": {
                "user": {"id": 123},
                "bot": {"id": 789, "username": username},
            }
        }
        self.service.handle(event)
        self.service.handle(event)  # token updates preserve the budget
        record = self.repo.get("bot:789")
        self.assertEqual(record["recipient_username"], "some_user")
        self.assertEqual(record["recipient_id"], 456)
        self.api.call.assert_any_call(
            "setManagedBotAccessSettings",
            user_id=789,
            is_access_restricted=False,
        )
        self.assertEqual(record["access_status"], "awaiting_claim")
        self.assertTrue(record["claim_token"])
        self.assertIn(f"t.me/{username}?start=claim_", self.service.invitation(record))
        self.assertEqual(record["owner_id"], 123)
        self.assertEqual(record["remaining_seconds"], 600)
        self.assertEqual(record["token"], "secret-token")
        self.assertNotIn(pending_key, self.repo.data)
        self.assertTrue(
            all(
                c.args[0]
                in (
                    "sendMessage",
                    "getMe",
                    "getManagedBotToken",
                    "setManagedBotAccessSettings",
                    "getManagedBotAccessSettings",
                )
                for c in self.api.call.call_args_list
            )
        )

    def test_invalid_values_keep_dialogue(self):
        self.message("/create")
        for text in ("-1", "0", "bad name", "1.5", "²", str(2**53)):
            self.message(text)
            self.assertEqual(self.repo.get("draft")["step"], "recipient")
        self.select_user()
        self.assertEqual(self.repo.get("draft")["recipient_username"], "some_user")
        for text in ("-1", "0", "abc", "1.5"):
            self.message(text)
            self.assertEqual(self.repo.get("draft")["step"], "seconds")
        self.message("/cancel")
        self.assertIsNone(self.repo.get("draft"))

    def test_stale_selection_is_ignored(self):
        self.message("/create")
        self.select_user(request_id=-1)
        self.assertEqual(self.repo.get("draft")["step"], "recipient")

    def test_existing_recipient_adds_limit_without_creating_another_bot(self):
        self.repo.put(
            "bot:789",
            {
                "bot_id": 789,
                "username": "child_bot",
                "recipient_id": 456,
                "remaining_seconds": 600,
                "access_status": "configured",
            },
        )
        self.message("/create")
        self.select_user()
        self.assertEqual(self.repo.get("draft"), {"step": "add_limit", "bot_id": 789})
        self.message("250")
        self.assertIsNone(self.repo.get("draft"))
        self.assertEqual(self.repo.list_pending(), [])
        record = self.repo.get("bot:789")
        self.assertEqual(record["remaining_seconds"], 850)
        self.assertEqual(record["budget_seconds"], 850)
        self.assertIn("850", self.api.call.call_args.kwargs["text"])

    def test_pending_creation_adds_limit_to_same_username(self):
        self.message("/create")
        self.select_user()
        self.message("600")
        pending = self.repo.list_pending()[0]
        self.message("/create")
        self.select_user()
        self.assertEqual(self.repo.get("draft")["step"], "add_limit")
        self.message("200")
        self.assertIsNone(self.repo.get("draft"))
        self.assertEqual(len(self.repo.list_pending()), 1)
        request = self.api.call.call_args.kwargs["reply_markup"]["keyboard"][0][0]
        self.assertEqual(
            request["request_managed_bot"]["suggested_username"], pending["username"]
        )
        self.assertIn("800 секунд", self.api.call.call_args.kwargs["text"])
        self.assertEqual(self.repo.list_pending()[0]["remaining_seconds"], 800)

    def test_add_limit_rejects_invalid_and_overflow(self):
        self.repo.put(
            "bot:789",
            {
                "bot_id": 789,
                "username": "child_bot",
                "recipient_id": 456,
                "remaining_seconds": 2**52 - 1,
                "budget_seconds": 2**52 - 1,
            },
        )
        self.message("/create")
        self.select_user()
        for value in ("0", "-1", "abc", "2"):
            self.message(value)
            self.assertEqual(self.repo.get("draft")["step"], "add_limit")
            self.assertEqual(self.repo.get("bot:789")["remaining_seconds"], 2**52 - 1)
        self.message("1")
        self.assertEqual(self.repo.get("bot:789")["remaining_seconds"], 2**52)

    def test_child_claim_failure_can_be_retried_without_username(self):
        record = {
            "bot_id": 789,
            "username": "child_bot",
            "remaining_seconds": 600,
            "access_status": "awaiting_claim",
            "claim_token": "one_time_token",
        }
        self.repo.put("bot:789", record)
        child_api = Mock()
        message = {
            "from": {"id": 456},
            "text": "/start claim_one_time_token",
        }
        original = self.api.call.side_effect

        def fail(method, **kwargs):
            if method == "setManagedBotAccessSettings":
                raise RuntimeError("unavailable")
            return original(method, **kwargs)

        self.api.call.side_effect = fail
        self.assertFalse(self.claim_from_child(record, message, child_api))
        self.assertEqual(record["access_status"], "needs_recipient_start")
        self.assertEqual(record["claim_token"], "one_time_token")
        self.assertIn("Не удалось", child_api.call.call_args.kwargs["text"])
        self.api.call.side_effect = original
        self.assertTrue(self.claim_from_child(record, message, child_api))
        self.assertEqual(record["access_status"], "configured")
        self.assertEqual(record["recipient_id"], 456)
        self.assertEqual(record["recipient_username"], "")
        self.assertNotIn("claim_token", record)

    def test_registration_preserves_existing_access_and_claim_state(self):
        for status in ("configured", "awaiting_claim", "needs_recipient_start"):
            with self.subTest(status=status):
                record = {
                    "bot_id": 789,
                    "username": "child_bot",
                    "name": "Child",
                    "token": "old-token",
                    "recipient_id": 456,
                    "remaining_seconds": 600,
                    "access_status": status,
                    "claim_update_offset": 42,
                }
                if status != "configured":
                    record["claim_token"] = "existing-link"
                self.repo.put("bot:789", record)
                self.api.reset_mock()
                self.service.register(
                    {"id": 789, "username": "renamed_bot", "first_name": "New name"}
                )
                saved = self.repo.get("bot:789")
                for field in (
                    "recipient_id",
                    "remaining_seconds",
                    "access_status",
                    "claim_update_offset",
                    "claim_token",
                ):
                    self.assertEqual(saved.get(field), record.get(field))
                self.assertEqual(saved["token"], "secret-token")
                self.assertEqual(saved["username"], "renamed_bot")
                self.assertFalse(
                    any(
                        c.args[0] == "setManagedBotAccessSettings"
                        for c in self.api.call.call_args_list
                    )
                )

    def test_polling_retries_failed_claim_and_stops_after_success(self):
        import tempfile
        from types import SimpleNamespace
        from pathlib import Path
        from bot_factories.admin_bot import repository as routes
        from bot_factories.admin_bot.repository import Repository

        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            repo = Repository(cache / "admin.sqlite3")
            repo.put(
                "bot:789",
                {
                    "bot_id": 789,
                    "username": "child_bot",
                    "token": "child-token",
                    "recipient_id": 999,
                    "remaining_seconds": 600,
                    "access_status": "awaiting_claim",
                    "claim_token": "one_time_token",
                },
            )
            child = Mock()
            child.call.side_effect = lambda method, **kw: (
                [
                    {
                        "update_id": kw["offset"],
                        "message": {
                            "from": {"id": 456},
                            "text": "/start claim_one_time_token",
                        },
                    }
                ]
                if method == "getUpdates"
                else True
            )
            original = self.api.call.side_effect

            def fail(method, **kwargs):
                if method == "setManagedBotAccessSettings":
                    raise RuntimeError("unavailable")
                return original(method, **kwargs)

            with patch.object(routes, "cache_folder", cache), patch.object(
                routes,
                "get_admin_bot_settings",
                return_value=SimpleNamespace(token="admin-token", owner_id=123),
            ), patch.object(
                routes,
                "TelegramAPI",
                side_effect=lambda token: child if token == "child-token" else self.api,
            ):
                self.api.call.side_effect = fail
                self.assertEqual(routes.process_claim_updates(notify_child_claim), 1)
                saved = repo.get("bot:789")
                self.assertEqual(saved["access_status"], "needs_recipient_start")
                self.assertEqual(saved["claim_token"], "one_time_token")
                self.assertEqual(saved["claim_update_offset"], 1)
                self.api.call.side_effect = original
                self.assertEqual(routes.process_claim_updates(notify_child_claim), 1)
                saved = repo.get("bot:789")
                self.assertEqual(saved["access_status"], "configured")
                self.assertEqual(saved["recipient_id"], 456)
                self.assertEqual(saved["remaining_seconds"], 600)
                self.assertNotIn("claim_token", saved)
                child.reset_mock()
                self.assertEqual(routes.process_claim_updates(notify_child_claim), 0)
                child.call.assert_not_called()
            repo.db.close()

    def test_unassigned_recipient_start_reports_actual_id(self):
        self.repo.put(
            "bot:789",
            {
                "bot_id": 789,
                "username": "child_bot",
                "recipient_id": 456,
                "remaining_seconds": 600,
            },
        )
        self.message("/start", user=457, chat=457)
        self.api.call.assert_called_once()
        self.assertEqual(self.api.call.call_args.kwargs["chat_id"], 457)
        self.assertIn("457", self.api.call.call_args.kwargs["text"])

    def test_unconfirmed_access_waits_for_recipient_start(self):
        self.repo.put(
            "bot:789",
            {
                "bot_id": 789,
                "username": "child_bot",
                "manager_username": "manager_bot",
                "recipient_id": 456,
                "recipient_username": "alice",
                "remaining_seconds": 600,
            },
        )
        original = self.api.call.side_effect

        def unavailable(method, **kwargs):
            if method == "getManagedBotAccessSettings":
                return {"is_access_restricted": True, "added_users": []}
            return original(method, **kwargs)

        self.api.call.side_effect = unavailable
        self.assertFalse(self.service.bots.grant_access(self.repo.get("bot:789")))
        self.assertEqual(
            self.repo.get("bot:789")["access_status"], "needs_recipient_start"
        )
        self.assertIn("Start", self.service.describe(self.repo.get("bot:789")))
        button = self.service.share_keyboard(self.repo.get("bot:789"))[
            "inline_keyboard"
        ][0][0]
        self.assertIn("t.me/alice", button["url"])
        from urllib.parse import parse_qs, urlsplit

        invitation = parse_qs(urlsplit(button["url"]).query)["text"][0]
        self.assertIn("Ваш персональный бот готов", invitation)
        self.assertIn("t.me/child_bot?start=claim_", invitation)
        self.assertNotIn("activate_789", invitation)
        self.api.call.side_effect = original
        self.message("/start", user=456, chat=456)
        self.assertEqual(self.repo.get("bot:789")["access_status"], "configured")
        self.api.call.assert_any_call(
            "sendMessage",
            chat_id=456,
            text=self.service.invitation(self.repo.get("bot:789")),
            reply_markup={
                "inline_keyboard": [
                    [{"text": "Открыть своего бота", "url": "https://t.me/child_bot"}]
                ]
            },
        )

    def test_claim_link_assigns_actual_sender_once(self):
        original = self.api.call.side_effect

        def access_for_claimant(method, **kwargs):
            if method == "getManagedBotAccessSettings":
                return {
                    "is_access_restricted": True,
                    "added_users": [{"id": 457}],
                }
            return original(method, **kwargs)

        self.api.call.side_effect = access_for_claimant
        record = {
            "bot_id": 789,
            "username": "child_bot",
            "manager_username": "manager_bot",
            "recipient_id": 456,
            "recipient_username": "selected_user",
            "remaining_seconds": 600,
            "access_status": "needs_recipient_start",
            "claim_token": "one_time_token",
        }
        self.repo.put("bot:789", record)

        self.service.handle(
            {
                "message": {
                    "from": {
                        "id": 457,
                        "username": "actual_user",
                        "first_name": "Bob",
                    },
                    "chat": {"id": 457},
                    "text": "/start claim_one_time_token",
                }
            }
        )

        saved = self.repo.get("bot:789")
        self.assertEqual(saved["recipient_id"], 457)
        self.assertEqual(saved["recipient_username"], "actual_user")
        self.assertEqual(saved["access_status"], "configured")
        self.assertNotIn("claim_token", saved)
        self.api.call.assert_any_call(
            "setManagedBotAccessSettings",
            user_id=789,
            is_access_restricted=True,
            added_user_ids=[457],
        )
        self.api.call.assert_any_call(
            "sendMessage",
            chat_id=457,
            text="Готово! Доступ активирован.",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "Открыть моего бота",
                            "url": "https://t.me/child_bot",
                        }
                    ]
                ]
            },
        )

        self.api.reset_mock()
        self.message("/start claim_one_time_token", user=458, chat=458)
        self.api.call.assert_called_once_with(
            "sendMessage",
            chat_id=458,
            text="Ссылка недействительна или уже использована.",
        )

    def test_personal_bot_claim_restricts_access_to_actual_sender(self):
        original = self.api.call.side_effect

        def access_for_claimant(method, **kwargs):
            if method == "getManagedBotAccessSettings":
                return {
                    "is_access_restricted": True,
                    "added_users": [{"id": 457}],
                }
            return original(method, **kwargs)

        self.api.call.side_effect = access_for_claimant
        record = {
            "bot_id": 789,
            "username": "child_bot",
            "token": "child-token",
            "remaining_seconds": 600,
            "access_status": "awaiting_claim",
            "claim_token": "one_time_token",
        }
        self.repo.put("bot:789", record)
        child_api = Mock()

        claimed = self.claim_from_child(
            record,
            {
                "from": {
                    "id": 457,
                    "username": "actual_user",
                    "first_name": "Bob",
                },
                "text": "/start claim_one_time_token",
            },
            child_api,
        )

        self.assertTrue(claimed)
        self.assertEqual(record["recipient_id"], 457)
        self.assertEqual(record["access_status"], "configured")
        self.assertNotIn("claim_token", record)
        self.api.call.assert_any_call(
            "setManagedBotAccessSettings",
            user_id=789,
            is_access_restricted=True,
            added_user_ids=[457],
        )
        child_api.call.assert_called_once_with(
            "sendMessage",
            chat_id=457,
            text="Готово! Это твой персональный бот.",
        )

    def test_invitation_targets_assigned_user(self):
        from urllib.parse import urlsplit, parse_qs

        bot = {
            "username": "child_bot",
            "name": "Personal & Test",
            "recipient_username": "alice",
            "recipient_id": 456,
            "remaining_seconds": 600,
            "access_status": "configured",
        }
        button = self.service.share_keyboard(bot)["inline_keyboard"][0][0]
        url = urlsplit(button["url"])
        self.assertEqual(url.path, "/alice")
        draft = parse_qs(url.query)["text"][0]
        self.assertIn("Personal & Test", draft)
        self.assertIn("600", draft)
        self.assertIn("https://t.me/child_bot", draft)
        del bot["recipient_username"]
        buttons = self.service.share_keyboard(bot)["inline_keyboard"]
        self.assertEqual(buttons[0][0]["copy_text"]["text"], draft)
        self.assertEqual(buttons[1][0]["url"], "tg://user?id=456")

    def test_foreign_creation_cannot_claim_pending(self):
        self.service.handle({"managed_bot": {"user": {"id": 456}, "bot": {"id": 1}}})
        self.api.call.assert_not_called()

    def test_unknown_username_is_not_bound(self):
        self.service.handle(
            {
                "managed_bot": {
                    "user": {"id": 123},
                    "bot": {"id": 1, "username": "changed_bot"},
                }
            }
        )
        self.assertIsNone(self.repo.get("bot:1"))

    def test_sqlite_persists_parameters(self):
        import tempfile
        from pathlib import Path
        from bot_factories.admin_bot.repository import Repository

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "admin.sqlite3"
            repo = Repository(path)
            repo.put("bot:1", {"recipient_id": 456, "remaining_seconds": 600})
            repo.put("pending:new_bot", {"recipient_id": 789, "username": "new_bot"})
            repo.put("draft", {"step": "seconds"})
            repo.db.close()
            reopened = Repository(path)
            self.assertEqual(reopened.get("bot:1")["remaining_seconds"], 600)
            self.assertEqual(len(reopened.list_bots()), 1)
            self.assertEqual(reopened.list_pending()[0]["recipient_id"], 789)
            reopened.delete("draft")
            self.assertIsNone(reopened.get("draft"))
            reopened.db.close()

    def test_admin_worker_registers_default_queue_task(self):
        from shared.config import settings
        from worker.celery_factory import TELEGRAM_UPDATE_QUEUE, TELEGRAM_UPDATE_TASK

        with patch.object(settings, "telegram_token", "123456:test-token"):
            from bot_factories.admin_bot import celery_app as admin_worker

        self.assertEqual(
            admin_worker.celery_app.conf.task_default_queue, TELEGRAM_UPDATE_QUEUE
        )
        self.assertIn(TELEGRAM_UPDATE_TASK, admin_worker.celery_app.tasks)
        update = {
            "update_id": 17,
            "managed_bot": {
                "user": {"id": 123, "is_bot": False, "first_name": "Owner"},
                "bot": {"id": 789, "is_bot": True, "first_name": "Child"},
            },
        }
        from bot_factories.admin_bot import telegram_routes

        with patch.dict(
            "os.environ",
            {"ADMIN_BOT_OWNER_ID": "123", "ADMIN_BOT_TOKEN": "123456:test-token"},
        ), patch.object(telegram_routes, "Repository") as repository, patch.object(
            telegram_routes, "TelegramAPI"
        ) as api, patch.object(
            telegram_routes, "AdminService"
        ) as service:
            result = admin_worker.celery_app.tasks[TELEGRAM_UPDATE_TASK].run(update)
        self.assertEqual(result, {"status": "ok"})
        service.return_value.handle.assert_called_once()
        self.assertEqual(
            service.return_value.handle.call_args.args[0]["managed_bot"]["bot"]["id"],
            789,
        )
        repository.return_value.db.close.assert_called_once()

    def test_admin_route_closes_repository(self):
        from bot_factories.admin_bot import telegram_routes

        update = {"update_id": 17, "message": {"text": "/start"}}
        with patch.dict(
            "os.environ", {"ADMIN_BOT_OWNER_ID": "123", "ADMIN_BOT_TOKEN": "test-token"}
        ), patch.object(telegram_routes, "Repository") as repo, patch.object(
            telegram_routes, "TelegramAPI"
        ) as api, patch.object(
            telegram_routes, "AdminService"
        ) as service:
            telegram_routes.process_telegram_update(update)
        api.assert_called_once_with("test-token")
        service.assert_called_once_with(api.return_value, repo.return_value, 123)
        service.return_value.handle.assert_called_once_with(update)
        repo.return_value.db.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
