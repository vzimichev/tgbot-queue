import secrets

from bot_factories.admin_bot.config import admin_settings
from bot_factories.admin_bot.telegram_api import telegram_call
from shared.bot_registry import BotRegistry


def creation_keyboard():
    suffix = secrets.token_hex(5)
    return {
        "keyboard": [
            [
                {
                    "text": "Создать эхо-бота",
                    "request_managed_bot": {
                        "request_id": 1,
                        "suggested_name": f"Echo {suffix.upper()}",
                        "suggested_username": f"echo_{suffix}_bot",
                    },
                }
            ],
            [{"text": "Мои боты"}],
        ],
        "resize_keyboard": True,
    }


class AdminService:
    def __init__(self, registry=None, call=telegram_call, config=admin_settings):
        self.registry = registry if registry is not None else BotRegistry()
        self.call = call
        self.config = config

    async def reply(self, text, **kwargs):
        return await self.call(
            self.config.token,
            "sendMessage",
            chat_id=self.config.owner_id,
            text=text,
            **kwargs,
        )

    async def connect(self, bot):
        bot_id = bot["id"]
        record = self.registry.get(bot_id)
        if record and record["owner_id"] != self.config.owner_id:
            return
        record = record or {
            "id": bot_id,
            "owner_id": self.config.owner_id,
            "kind": "echo",
            "secret": secrets.token_urlsafe(32),
        }
        record.update(username=bot.get("username", str(bot_id)), status="connecting")
        self.registry.save(record)
        try:
            token = await self.call(
                self.config.token, "getManagedBotToken", user_id=bot_id
            )
            identity = await self.call(token, "getMe")
            if identity["id"] != bot_id:
                raise ValueError("Managed bot identity mismatch")
            await self.call(
                token,
                "setWebhook",
                url=f"{self.config.public_base_url.rstrip('/')}/webhook/managed/{bot_id}",
                secret_token=record["secret"],
                allowed_updates=["message"],
            )
        except Exception:
            record["status"] = "error"
            self.registry.save(record)
            await self.reply(
                f"Не удалось подключить @{record['username']}. "
                f"Повторить: /retry {bot_id}"
            )
            return
        record["status"] = "active"
        self.registry.save(record)
        await self.reply(
            f"Эхо-бот подключён: https://t.me/{record['username']}",
            reply_markup=creation_keyboard(),
        )

    async def handle(self, update):
        # managed_bot also reports ownership/token changes. Never accept a new owner.
        managed = update.get("managed_bot")
        if managed:
            if managed.get("user", {}).get("id") != self.config.owner_id:
                record = self.registry.get(managed["bot"]["id"])
                if record:
                    record["status"] = "disabled"
                    self.registry.save(record)
                return
            await self.connect(managed["bot"])
            return
        message = update.get("message", {})
        if (
            message.get("from", {}).get("id") != self.config.owner_id
            or message.get("chat", {}).get("type") != "private"
            or self.config.owner_id <= 0
        ):
            return
        # Creation is processed via managed_bot only; the companion service
        # message must not trigger a second registration.
        text = message.get("text", "")
        if text in ("/start", "/create", "Создать эхо-бота"):
            await self.reply(
                "Создай эхо-бота или открой список:",
                reply_markup=creation_keyboard(),
            )
        elif text in ("/bots", "Мои боты"):
            records = [
                r for r in self.registry.list() if r["owner_id"] == self.config.owner_id
            ]
            if not records:
                await self.reply("Пока нет созданных ботов.")
            for record in records:
                await self.reply(
                    f"@{record['username']} — {record['status']}\n"
                    f"Повторить подключение: /retry {record['id']}"
                )
        elif text.startswith("/retry "):
            try:
                record = self.registry.get(int(text.split()[1]))
            except (ValueError, IndexError):
                record = None
            if record and record["owner_id"] == self.config.owner_id:
                await self.connect(record)
            else:
                await self.reply("Бот не найден.")
