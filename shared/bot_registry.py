"""Persistent managed-bot metadata; Telegram bot tokens are never stored here."""

import json

from redis import Redis

from shared.config import settings

MANAGED_ECHO_TASK = "managed_echo.process_telegram_update"
MANAGED_ECHO_QUEUE = "managed_echo"
ADMIN_TASK = "admin_bot.process_telegram_update"
ADMIN_QUEUE = "admin_bot"


class BotRegistry:
    def __init__(self, client=None):
        self.client = (
            client
            if client is not None
            else Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password,
                db=3,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
        )

    def get(self, bot_id):
        value = self.client.hget("managed_bots", str(bot_id))
        return json.loads(value) if value else None

    def save(self, record):
        self.client.hset("managed_bots", str(record["id"]), json.dumps(record))

    def list(self):
        return sorted(
            (json.loads(value) for value in self.client.hvals("managed_bots")),
            key=lambda item: item["id"],
        )
