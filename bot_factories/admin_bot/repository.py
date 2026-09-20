import json
import logging
import os
import sqlite3

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
