import unittest
from unittest.mock import Mock


from bot_factories.admin_bot.service import AdminService


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
        self.assertIsInstance(request["request_id"], int)
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
            is_access_restricted=True,
            added_user_ids=[456],
        )
        self.assertEqual(record["access_status"], "configured")
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

    def test_existing_recipient_does_not_get_another_bot(self):
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
        self.assertIsNone(self.repo.get("draft"))
        self.assertEqual(self.repo.list_pending(), [])
        self.assertIn("уже создан", self.api.call.call_args.kwargs["text"])

    def test_pending_creation_reuses_same_username_and_budget(self):
        self.message("/create")
        self.select_user()
        self.message("600")
        pending = self.repo.list_pending()[0]
        self.message("/create")
        self.select_user()
        self.assertIsNone(self.repo.get("draft"))
        self.assertEqual(len(self.repo.list_pending()), 1)
        request = self.api.call.call_args.kwargs["reply_markup"]["keyboard"][0][0]
        self.assertEqual(
            request["request_managed_bot"]["suggested_username"], pending["username"]
        )
        self.assertIn("600 секунд", self.api.call.call_args.kwargs["text"])

    def test_access_cannot_assign_second_bot_to_same_recipient(self):
        self.repo.put(
            "bot:789",
            {
                "bot_id": 789,
                "username": "first_bot",
                "recipient_id": 456,
                "remaining_seconds": 600,
                "access_status": "configured",
            },
        )
        self.repo.put(
            "bot:790",
            {"bot_id": 790, "username": "second_bot", "remaining_seconds": 600},
        )
        self.message("/access 790")
        self.select_user()
        self.assertIsNone(self.repo.get("bot:790").get("recipient_id"))
        self.assertIsNone(self.repo.get("draft"))
        self.assertFalse(
            any(
                call.args[0] == "setManagedBotAccessSettings"
                for call in self.api.call.call_args_list
            )
        )

    def test_existing_bot_can_get_access_without_username(self):
        self.repo.put(
            "bot:789",
            {"bot_id": 789, "username": "child_bot", "remaining_seconds": 600},
        )
        self.message("/access 789")
        self.select_user(username="")
        self.api.call.assert_any_call(
            "setManagedBotAccessSettings",
            user_id=789,
            is_access_restricted=True,
            added_user_ids=[456],
        )
        self.assertEqual(self.repo.get("bot:789")["access_status"], "configured")

    def test_access_failure_does_not_report_success(self):
        self.repo.put(
            "bot:789",
            {"bot_id": 789, "username": "child_bot", "remaining_seconds": 600},
        )
        self.message("/access 789")
        original = self.api.call.side_effect

        def fail(method, **kwargs):
            if method == "setManagedBotAccessSettings":
                raise RuntimeError("unavailable")
            return original(method, **kwargs)

        self.api.call.side_effect = fail
        with self.assertRaises(RuntimeError):
            self.select_user()
        self.assertEqual(self.repo.get("bot:789")["access_status"], "pending")
        self.api.call.side_effect = original
        self.select_user()
        self.assertEqual(self.repo.get("bot:789")["access_status"], "configured")

    def test_access_must_be_confirmed_by_telegram(self):
        self.repo.put(
            "bot:789",
            {"bot_id": 789, "username": "child_bot", "remaining_seconds": 600},
        )
        self.message("/access 789")
        original = self.api.call.side_effect

        def missing_user(method, **kwargs):
            if method == "getManagedBotAccessSettings":
                return {"is_access_restricted": True}
            return original(method, **kwargs)

        self.api.call.side_effect = missing_user
        self.select_user()
        self.assertEqual(self.repo.get("bot:789")["access_status"], "pending")
        self.assertIn(
            "пока не подтвердил", self.api.call.call_args_list[-1].kwargs["text"]
        )

        self.api.call.side_effect = original
        self.message("/start", user=456, chat=456)
        self.assertEqual(self.repo.get("bot:789")["access_status"], "configured")
        self.api.call.assert_any_call("getManagedBotAccessSettings", user_id=789)

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


if __name__ == "__main__":
    unittest.main()
