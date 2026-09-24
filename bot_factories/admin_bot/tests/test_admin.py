import unittest
from unittest.mock import Mock, patch


import asyncio
import copy
from types import SimpleNamespace
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from unittest.mock import AsyncMock
from bot_factories.admin_bot import telegram_routes as routes
from bot_factories.admin_bot.repository import BotRepository
from bot_factories.admin_bot.telegram_routes import notify_child_claim


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
        self.bots = BotRepository(self.api, self.repo, 123)
        self.runner = asyncio.Runner()
        self.addCleanup(self.runner.close)
        self.dp = Dispatcher()
        router = copy.deepcopy(
            routes.admin_router, {id(routes.admin_router.parent_router): None}
        )
        router._parent_router = None
        self.dp.include_router(router)
        self.bot = Bot("123456:test-token")

        async def send(bot, method, **kwargs):
            payload = method.model_dump(exclude_none=True, exclude_defaults=True)
            payload.pop("parse_mode", None)
            self.api.call(method.__api_method__, **payload)
            return True

        self.bot.session = AsyncMock(side_effect=send)
        self.context = self.dp.fsm.get_context(bot=self.bot, chat_id=123, user_id=123)
        settings = patch.object(
            routes, "get_admin_bot_settings", return_value=SimpleNamespace(owner_id=123)
        )
        settings.start()
        self.addCleanup(settings.stop)
        operations = patch.object(
            routes,
            "run_bot_operation",
            side_effect=lambda callback: callback(self.bots),
        )
        operations.start()
        self.addCleanup(operations.stop)
        self.addCleanup(lambda: self.runner.run(self.dp.storage.close()))

    def draft(self):
        state = self.runner.run(self.context.get_state())
        if state is None:
            return None
        data = self.runner.run(self.context.get_data())
        step = state.split(":")[-1]
        if step == "add_limit":
            key = data.pop("key")
            data.update(
                {"bot_id": int(key[4:])}
                if key.startswith("bot:")
                else {"pending_username": key[8:]}
            )
        return {"step": step, **data}

    def feed(self, body):
        body = copy.deepcopy(body)
        body["update_id"] = 17
        if "message" in body:
            msg = body["message"]
            msg.update(message_id=1, date=0)
            msg["chat"].update(type="private" if msg["chat"]["id"] > 0 else "group")
            msg["from"].update(is_bot=False, first_name="Test")
        if "managed_bot" in body:
            body["managed_bot"]["user"].update(is_bot=False, first_name="Owner")
            body["managed_bot"]["bot"].update(is_bot=True, first_name="Child")
        return self.runner.run(
            self.dp.feed_update(self.bot, Update.model_validate(body))
        )

    def claim_from_child(self, record, message, child_api):
        result = self.bots.claim_from_message(record, message)
        notify_child_claim(message, child_api, result)
        return result == "configured"

    def message(self, text, user=123, chat=123):
        self.feed(
            {"message": {"from": {"id": user}, "chat": {"id": chat}, "text": text}}
        )

    def select_user(self, username="some_user", request_id=None):
        self.feed(
            {
                "message": {
                    "from": {"id": 123},
                    "chat": {"id": 123},
                    "users_shared": {
                        "request_id": (
                            request_id
                            if request_id is not None
                            else self.draft()["request_id"]
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
        self.message("Выбрать пользователя", user=456)
        self.message("Выбрать пользователя", chat=-456)
        self.api.call.assert_not_called()
        self.assertEqual(self.repo.data, {})

    def test_creation_persists_parameters_without_child_calls(self):
        self.message("Выбрать пользователя")
        self.select_user()
        self.message("Создать бота")
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
        self.feed(event)
        self.feed(event)  # token updates preserve the budget
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
        self.assertIn(f"t.me/{username}?start=claim_", routes.invitation(record))
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
        self.message("Выбрать пользователя")
        for text in ("-1", "0", "bad name", "1.5", "²", str(2**53)):
            self.message(text)
            self.assertEqual(self.draft()["step"], "recipient")
        self.select_user()
        self.message("Создать бота")
        self.assertEqual(self.draft()["recipient_username"], "some_user")
        for text in ("-1", "0", "abc", "1.5"):
            self.message(text)
            self.assertEqual(self.draft()["step"], "seconds")
        self.message("Назад")
        self.assertEqual(self.draft()["step"], "card")
        self.message("Назад")
        self.assertIsNone(self.draft())

    def test_stale_selection_is_ignored(self):
        self.message("Выбрать пользователя")
        self.select_user(request_id=-1)
        self.assertEqual(self.draft()["step"], "recipient")

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
                self.bots.register(
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
        self.assertFalse(self.bots.grant_access(self.repo.get("bot:789")))
        self.assertEqual(
            self.repo.get("bot:789")["access_status"], "needs_recipient_start"
        )
        self.assertIn("Start", routes.describe(self.repo.get("bot:789")))
        button = routes.share_keyboard(self.repo.get("bot:789"))["inline_keyboard"][0][
            0
        ]
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
            text=routes.invitation(self.repo.get("bot:789")),
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

        self.feed(
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
        button = routes.share_keyboard(bot)["inline_keyboard"][0][0]
        url = urlsplit(button["url"])
        self.assertEqual(url.path, "/alice")
        draft = parse_qs(url.query)["text"][0]
        self.assertIn("Personal & Test", draft)
        self.assertIn("600", draft)
        self.assertIn("https://t.me/child_bot", draft)
        del bot["recipient_username"]
        buttons = routes.share_keyboard(bot)["inline_keyboard"]
        self.assertEqual(buttons[0][0]["copy_text"]["text"], draft)
        self.assertEqual(buttons[1][0]["url"], "tg://user?id=456")

    def test_foreign_creation_cannot_claim_pending(self):
        self.feed({"managed_bot": {"user": {"id": 456}, "bot": {"id": 1}}})
        self.api.call.assert_not_called()

    def test_unknown_username_is_not_bound(self):
        self.feed(
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

    def test_run_operation_closes_repository_on_error(self):
        from bot_factories.admin_bot import repository

        with patch.object(
            repository,
            "get_admin_bot_settings",
            return_value=SimpleNamespace(token="test", owner_id=123),
        ), patch.object(repository, "Repository") as repo:

            def fail(bots):
                raise RuntimeError("operation failed")

            with self.assertRaisesRegex(RuntimeError, "operation failed"):
                repository.run_bot_operation(fail)
            repo.return_value.db.close.assert_called_once()

    def test_other_users_cannot_advance_owner_dialogue(self):
        self.message("Выбрать пользователя")
        self.select_user()
        self.message("Создать бота")
        self.api.reset_mock()
        self.message("600", user=456, chat=456)
        self.message("Назад", user=456, chat=456)
        self.message("Все боты", user=456, chat=456)
        self.assertEqual(self.draft()["step"], "seconds")
        self.assertEqual(self.repo.list_pending(), [])
        self.api.call.assert_not_called()

    def test_admin_worker_dispatches_commands_and_managed_events(self):
        from shared.config import settings
        from worker.celery_factory import TELEGRAM_UPDATE_QUEUE, TELEGRAM_UPDATE_TASK

        with patch.object(settings, "telegram_token", "123456:test-token"):
            from bot_factories.admin_bot import celery_app as worker
        app = worker.celery_app
        self.assertEqual(app.conf.task_default_queue, TELEGRAM_UPDATE_QUEUE)
        with patch.object(app, "dp", self.dp), patch.object(
            app, "bot", self.bot
        ), patch.object(
            app, "telegram_event_loop", self.runner.get_loop(), create=True
        ):
            result = app.tasks[TELEGRAM_UPDATE_TASK].run(
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 1,
                        "date": 0,
                        "text": "Выбрать пользователя",
                        "from": {"id": 123, "is_bot": False, "first_name": "Owner"},
                        "chat": {"id": 123, "type": "private"},
                    },
                }
            )
            self.assertEqual(result, {"status": "ok"})
            self.assertEqual(self.draft()["step"], "recipient")
            self.select_user()
            self.message("Создать бота")
            self.message("600")
            username = self.repo.list_pending()[0]["username"]
            app.tasks[TELEGRAM_UPDATE_TASK].run(
                {
                    "update_id": 2,
                    "managed_bot": {
                        "user": {"id": 123, "is_bot": False, "first_name": "Owner"},
                        "bot": {
                            "id": 789,
                            "is_bot": True,
                            "first_name": "Child",
                            "username": username,
                        },
                    },
                }
            )
            self.assertEqual(
                self.repo.get("bot:789")["access_status"], "awaiting_claim"
            )

    def test_start_clears_dialogue_and_non_text_budget_is_rejected(self):
        self.message("Выбрать пользователя")
        self.select_user()
        self.message("Создать бота")
        self.feed({"message": {"from": {"id": 123}, "chat": {"id": 123}}})
        self.assertEqual(self.draft()["step"], "seconds")
        self.message("/start")
        self.assertIsNone(self.draft())

    def test_card_new_pending_and_back(self):
        self.message("/start")
        self.assertEqual(
            routes.main_keyboard()["keyboard"],
            [[{"text": "Выбрать пользователя"}], [{"text": "Все боты"}]],
        )
        self.message("Выбрать пользователя")
        self.select_user()
        self.assertEqual(self.draft()["step"], "card")
        self.assertIn("не создан", self.api.call.call_args.kwargs["text"])
        self.message("600")
        self.assertEqual(self.repo.list_pending(), [])
        self.message("Создать бота")
        self.message("600")
        pending = self.repo.list_pending()[0].copy()
        self.message("Назад")
        self.assertIsNone(self.draft())
        self.message("Выбрать пользователя")
        self.select_user()
        self.assertIn("Заверши создание", self.api.call.call_args.kwargs["text"])
        self.message("Продолжить создание")
        request = self.api.call.call_args.kwargs["reply_markup"]["keyboard"][0][0]
        self.assertEqual(
            request["request_managed_bot"]["suggested_username"], pending["username"]
        )
        self.assertEqual(self.repo.list_pending(), [pending])

    def test_card_links_preserve_claim_and_limit(self):
        for status in ("awaiting_claim", "configured"):
            record = {
                "bot_id": 789,
                "username": "child_bot",
                "recipient_id": 456,
                "remaining_seconds": 600,
                "access_status": status,
            }
            if status != "configured":
                record["claim_token"] = "original"
            self.repo.put("bot:789", record.copy())
            self.message("Выбрать пользователя")
            self.select_user()
            text = self.api.call.call_args.kwargs["text"]
            self.assertIn("https://t.me/child_bot", text)
            self.assertEqual("?start=claim_original" in text, status != "configured")
            self.message("250")
            self.assertEqual(self.repo.get("bot:789"), record)
            self.message("Добавить лимит")
            self.assertEqual(self.draft()["step"], "add_limit")
            self.message("250")
            self.assertEqual(self.repo.get("bot:789")["remaining_seconds"], 850)
            self.assertEqual(self.draft()["step"], "card")
            self.assertEqual(self.repo.list_pending(), [])

    def test_budget_validation_and_back_does_not_mutate(self):
        self.repo.put(
            "bot:789",
            {
                "bot_id": 789,
                "username": "child_bot",
                "recipient_id": 456,
                "remaining_seconds": 2**52 - 1,
                "access_status": "configured",
            },
        )
        self.message("Выбрать пользователя")
        self.select_user()
        self.message("Добавить лимит")
        for value in ("0", "-1", "abc", "2"):
            self.message(value)
            self.assertEqual(self.draft()["step"], "add_limit")
            self.assertEqual(self.repo.get("bot:789")["remaining_seconds"], 2**52 - 1)
        self.message("Назад")
        self.assertEqual(self.draft()["step"], "card")
        self.message("Добавить лимит")
        self.message("1")
        self.assertEqual(self.repo.get("bot:789")["remaining_seconds"], 2**52)

    def test_restart_keeps_pending_creation(self):
        self.message("Выбрать пользователя")
        self.select_user()
        self.message("Создать бота")
        self.message("600")
        pending = self.repo.list_pending()[0].copy()
        from aiogram.fsm.storage.memory import MemoryStorage

        self.dp.fsm.storage = MemoryStorage()
        self.context = self.dp.fsm.get_context(bot=self.bot, chat_id=123, user_id=123)
        self.message("Выбрать пользователя")
        self.select_user()
        self.assertEqual(self.draft()["step"], "card")
        self.assertIn("Заверши создание", self.api.call.call_args.kwargs["text"])
        self.assertEqual(self.repo.list_pending(), [pending])


if __name__ == "__main__":
    unittest.main()
