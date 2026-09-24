import json
import logging
import os
import sqlite3
import secrets
from pathlib import Path

from bot_factories.admin_bot.config import get_admin_bot_settings

import httpx


class Repository:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        if str(path) != ":memory:":
            os.chmod(path, 0o600)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS records (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.db.commit()

    def get(self, key):
        row = self.db.execute(
            "SELECT value FROM records WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key, value):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO records VALUES (?, ?)", (key, json.dumps(value))
            )

    def delete(self, key):
        with self.db:
            self.db.execute("DELETE FROM records WHERE key = ?", (key,))

    def list_bots(self):
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT value FROM records WHERE key LIKE 'bot:%'"
            )
        ]

    def list_pending(self):
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT value FROM records WHERE key LIKE 'pending:%'"
            )
        ]


class TelegramAPI:
    def __init__(self, token):
        self.token = token

    def call(self, method, **payload):
        # HTTP client logs include the request URL, which contains the bot token.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        try:
            response = httpx.post(
                f"https://api.telegram.org/bot{self.token}/{method}",
                json=payload,
                timeout=30,
            )
            data = response.json()
            if response.is_success and data.get("ok"):
                return data["result"]
        except (httpx.HTTPError, ValueError):
            pass
        # Never propagate exceptions containing credential-bearing URLs.
        raise RuntimeError(f"Telegram API call failed: {method}") from None


logger = logging.getLogger(__name__)
cache_folder = Path(__file__).parent / ".cache"


class BotRepository:
    """Managed bot operations, independent of the admin dialogue."""

    def __init__(self, api, repository, owner_id):
        self.api = api
        self.repo = repository
        self.owner = owner_id

    def create_pending(self, recipient, seconds):
        username = f"personal_{secrets.token_hex(6)}_bot"
        record = {
            **{
                key: recipient[key]
                for key in ("recipient_username", "recipient_id", "recipient_name")
                if key in recipient
            },
            "remaining_seconds": seconds,
            "budget_seconds": seconds,
            "username": username,
            "name": "My faceswap bot",
        }
        self.repo.put(f"pending:{username}", record)
        return record

    def add_limit(self, key, seconds):
        record = self.repo.get(key)
        if record is None:
            raise LookupError(key)
        if not 0 < seconds <= 2**52 or record["remaining_seconds"] + seconds > 2**52:
            raise ValueError("Invalid budget")
        record["budget_seconds"] = (
            record.get("budget_seconds", record["remaining_seconds"]) + seconds
        )
        record["remaining_seconds"] += seconds
        self.repo.put(key, record)
        return record

    def register(self, bot):
        key = f"bot:{bot['id']}"
        existing = self.repo.get(key)
        username = bot.get("username", "")
        pending_key = f"pending:{username}"
        record = existing or self.repo.get(pending_key)
        if not record:
            return None
        token = self.api.call("getManagedBotToken", user_id=bot["id"])
        record = {
            **record,
            "bot_id": bot["id"],
            "username": username,
            "name": bot.get("first_name", record["name"]),
            "token": token,
            "manager_username": self.api.call("getMe")["username"],
            "owner_id": self.owner,
        }
        if existing:
            self.repo.put(key, record)
        else:
            self.prepare_claim(record)
        self.repo.delete(pending_key)
        return record

    def prepare_claim(self, record):
        self.api.call(
            "setManagedBotAccessSettings",
            user_id=record["bot_id"],
            is_access_restricted=False,
        )
        record["access_status"] = "awaiting_claim"
        self.ensure_claim_token(record)
        record.setdefault("claim_update_offset", 0)
        self.repo.put(f"bot:{record['bot_id']}", record)

    def grant_access(self, record):
        record["access_status"] = "pending"
        self.repo.put(f"bot:{record['bot_id']}", record)
        if not record.get("recipient_id"):
            record["access_status"] = "needs_recipient"
            self.ensure_claim_token(record)
            self.repo.put(f"bot:{record['bot_id']}", record)
            return False
        try:
            self.api.call(
                "setManagedBotAccessSettings",
                user_id=record["bot_id"],
                is_access_restricted=True,
                added_user_ids=[record["recipient_id"]],
            )
            settings = self.api.call(
                "getManagedBotAccessSettings", user_id=record["bot_id"]
            )
        except RuntimeError:
            logger.exception(
                "Could not grant managed bot access: bot_id=%s recipient_id=%s",
                record["bot_id"],
                record["recipient_id"],
            )
            record["access_status"] = "needs_recipient_start"
            self.ensure_claim_token(record)
            self.repo.put(f"bot:{record['bot_id']}", record)
            return False
        added_ids = {user["id"] for user in settings.get("added_users", [])}
        configured = (
            settings.get("is_access_restricted") is True
            and record["recipient_id"] in added_ids
        )
        record["access_status"] = (
            "configured" if configured else "needs_recipient_start"
        )
        if configured:
            record.pop("claim_token", None)
        else:
            self.ensure_claim_token(record)
        self.repo.put(f"bot:{record['bot_id']}", record)
        return configured

    @staticmethod
    def ensure_claim_token(record):
        if not record.get("claim_token"):
            record["claim_token"] = secrets.token_urlsafe(24)

    def find_claim(self, token):
        return next(
            (
                bot
                for bot in self.repo.list_bots()
                if bot.get("claim_token")
                and secrets.compare_digest(bot["claim_token"], token)
            ),
            None,
        )

    def activate_claim(self, record, sender, token):
        sender_id = sender.get("id")
        if (
            not record
            or not isinstance(sender_id, int)
            or sender_id <= 0
            or not token
            or not record.get("claim_token")
            or not secrets.compare_digest(record["claim_token"], token)
        ):
            return "invalid"
        record.update(
            recipient_id=sender_id,
            recipient_username=sender.get("username", ""),
            recipient_name=sender.get("first_name", ""),
        )
        return "configured" if self.grant_access(record) else "failed"

    def claim_from_message(self, record, message):
        parts = (message.get("text") or "").strip().split(maxsplit=1)
        token = (
            parts[1][len("claim_") :]
            if len(parts) == 2
            and parts[0].split("@")[0] == "/start"
            and parts[1].startswith("claim_")
            else ""
        )
        return self.activate_claim(record, message.get("from", {}), token)


def process_claim_updates(notify_claim) -> int:
    """Poll unclaimed managed bots until their one-time link is used."""
    settings = get_admin_bot_settings()
    if not settings.token or settings.owner_id <= 0:
        raise RuntimeError("ADMIN_BOT_TOKEN and ADMIN_BOT_OWNER_ID are required")

    cache_folder.mkdir(mode=0o700, exist_ok=True)
    repository = Repository(cache_folder / "admin.sqlite3")
    processed = 0
    try:
        service = BotRepository(
            TelegramAPI(settings.token), repository, settings.owner_id
        )
        for record in repository.list_bots():
            if record.get("access_status") == "configured" or not record.get(
                "claim_token"
            ):
                continue
            child_api = TelegramAPI(record["token"])
            try:
                updates = child_api.call(
                    "getUpdates",
                    offset=record.get("claim_update_offset", 0),
                    timeout=0,
                    allowed_updates=["message"],
                )
            except RuntimeError:
                logger.exception(
                    "Could not poll claim updates: bot_id=%s", record["bot_id"]
                )
                continue

            for update in updates:
                record["claim_update_offset"] = update["update_id"] + 1
                message = update.get("message")
                if message:
                    notify_claim(
                        message, child_api, service.claim_from_message(record, message)
                    )
                processed += 1
            repository.put(f"bot:{record['bot_id']}", record)
    finally:
        repository.db.close()
    return processed
