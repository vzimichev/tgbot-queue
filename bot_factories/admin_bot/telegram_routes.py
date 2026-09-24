import asyncio
import logging
import secrets
from pathlib import Path
from urllib.parse import quote, urlencode

from aiogram import Router
from aiogram.types import Message
from aiogram.types.managed_bot_updated import ManagedBotUpdated

from bot_factories.admin_bot.config import get_admin_bot_settings
from bot_factories.admin_bot.repository import Repository, TelegramAPI

logger = logging.getLogger(__name__)


class AdminService:
    def __init__(self, api, repository, owner_id):
        self.api = api
        self.repo = repository
        self.owner = owner_id

    def say(self, text, **kwargs):
        self.api.call("sendMessage", chat_id=self.owner, text=text, **kwargs)

    def handle(self, update):
        managed = update.get("managed_bot")
        if managed:
            if managed.get("user", {}).get("id") == self.owner:
                self.register(managed["bot"])
            return
        message = update.get("message", {})
        sender_id = message.get("from", {}).get("id")
        chat_id = message.get("chat", {}).get("id")
        recipient_text = (message.get("text") or "").strip()
        if sender_id is not None and sender_id == chat_id and sender_id != self.owner:
            parts = recipient_text.split(maxsplit=1)
            command = parts[0].split("@")[0] if recipient_text else ""
            if command == "/start":
                if len(parts) == 2 and parts[1].startswith("claim_"):
                    self.claim_bot(message, parts[1][len("claim_") :])
                    return
                matched = False
                for bot in self.repo.list_bots():
                    if bot.get("recipient_id") == sender_id:
                        matched = True
                        if self.grant_access(bot):
                            self.api.call(
                                "sendMessage",
                                chat_id=sender_id,
                                text=self.invitation(bot),
                                reply_markup={
                                    "inline_keyboard": [
                                        [
                                            {
                                                "text": "Открыть своего бота",
                                                "url": f"https://t.me/{bot['username']}",
                                            }
                                        ]
                                    ]
                                },
                            )
                        else:
                            self.api.call(
                                "sendMessage",
                                chat_id=sender_id,
                                text="Доступ пока не удалось настроить. Попробуй /start ещё раз.",
                            )
                if not matched and self.repo.list_bots():
                    self.api.call(
                        "sendMessage",
                        chat_id=sender_id,
                        text=(
                            "Этот аккаунт не назначен получателем бота. "
                            f"Твой Telegram ID: {sender_id}. "
                            "Передай его владельцу, чтобы он проверил выбор пользователя."
                        ),
                    )
                return
        if sender_id != self.owner or chat_id != self.owner:
            return
        if message.get("users_shared"):
            shared = message["users_shared"]
            draft = self.repo.get("draft")
            if (
                not draft
                or draft.get("step") != "recipient"
                or shared.get("request_id") != draft.get("request_id")
            ):
                self.say("Этот выбор устарел. Начни заново через /create.")
                return
            users = shared.get("users", [])
            if (
                len(users) != 1
                or not isinstance(users[0].get("user_id"), int)
                or users[0]["user_id"] <= 0
            ):
                self.say("Выбери одного пользователя.")
                return
            user = users[0]
            recipient = {
                "recipient_id": user["user_id"],
                "recipient_username": user.get("username", ""),
                "recipient_name": user.get("first_name", ""),
            }
            existing = next(
                (
                    bot
                    for bot in self.repo.list_bots()
                    if bot.get("recipient_id") == recipient["recipient_id"]
                ),
                None,
            )
            if existing:
                self.repo.put(
                    "draft", {"step": "add_limit", "bot_id": existing["bot_id"]}
                )
                self.say("Бот уже создан. Сколько секунд добавить к лимиту?")
                return
            pending = next(
                (
                    bot
                    for bot in self.repo.list_pending()
                    if bot.get("recipient_id") == recipient["recipient_id"]
                ),
                None,
            )
            if pending:
                self.repo.put(
                    "draft",
                    {"step": "add_limit", "pending_username": pending["username"]},
                )
                self.say(
                    "Создание бота уже начато. Сколько секунд добавить к лимиту?"
                )
                return
            self.repo.put("draft", {"step": "seconds", **recipient})
            self.say(
                "Как долго? Отправь бюджет в секундах, например 600.",
                reply_markup={"remove_keyboard": True},
            )
            return
        # Telegram also sends a companion service message; managed_bot registers it.
        if message.get("managed_bot_created"):
            return
        text = message.get("text", "").strip()
        command = text.split(maxsplit=1)[0].split("@")[0] if text else ""
        if command in ("/start", "/help"):
            self.say(
                "/create — создать бота или добавить лимит\n/bots — список ботов\n"
                "/cancel — отменить ввод\nБюджет задаётся в секундах и не списывается.",
                reply_markup={
                    "keyboard": [[{"text": "Создать бота"}]],
                    "resize_keyboard": True,
                },
            )
        elif command == "/bots":
            bots = self.repo.list_bots()
            if not bots:
                self.say("Пока нет созданных ботов.")
            for bot in bots:
                self.say(self.describe(bot), reply_markup=self.share_keyboard(bot))
        elif command == "/cancel":
            self.repo.delete("draft")
            self.say("Ввод отменён.")
        elif command == "/create" or text == "Создать бота":
            self.choose_recipient()
        else:
            draft = self.repo.get("draft")
            if not draft:
                self.say("Для создания бота используй /create.")
                return
            if draft["step"] == "recipient":
                self.say("Нажми кнопку «Выбрать пользователя».")
            else:
                if (
                    not text.isascii()
                    or not text.isdecimal()
                    or not 0 < int(text) <= 2**52
                ):
                    self.say("Введи положительное целое число секунд.")
                    return
                if draft["step"] == "add_limit":
                    key = (
                        f"bot:{draft['bot_id']}"
                        if draft.get("bot_id")
                        else f"pending:{draft['pending_username']}"
                    )
                    record = self.repo.get(key)
                    if not record:
                        self.repo.delete("draft")
                        self.say("Бот не найден. Начни заново через /create.")
                        return
                    increment = int(text)
                    if record["remaining_seconds"] + increment > 2**52:
                        self.say("Итоговый лимит слишком велик.")
                        return
                    record["budget_seconds"] = (
                        record.get("budget_seconds", record["remaining_seconds"])
                        + increment
                    )
                    record["remaining_seconds"] += increment
                    self.repo.put(key, record)
                    self.repo.delete("draft")
                    self.say(
                        f"Добавлено {increment} секунд. Новый лимит: {record['remaining_seconds']} секунд."
                    )
                    if key.startswith("pending:"):
                        self.send_creation_request(record)
                    return
                if self.recipient_taken(draft["recipient_id"]):
                    self.repo.delete("draft")
                    return
                username = f"personal_{secrets.token_hex(6)}_bot"
                pending = {
                    **{
                        key: draft[key]
                        for key in (
                            "recipient_username",
                            "recipient_id",
                            "recipient_name",
                        )
                        if key in draft
                    },
                    "remaining_seconds": int(text),
                    "budget_seconds": int(text),
                    "username": username,
                    "name": "My faceswap bot",
                }
                self.repo.put(f"pending:{username}", pending)
                self.send_creation_request(pending)
                self.repo.delete("draft")

    def recipient_taken(self, recipient_id):
        for bot in self.repo.list_bots():
            if bot.get("recipient_id") == recipient_id:
                self.say(
                    "Для этого пользователя бот уже создан.\n" + self.describe(bot),
                    reply_markup=self.share_keyboard(bot),
                )
                return True
        for pending in self.repo.list_pending():
            if pending.get("recipient_id") == recipient_id:
                self.say("Для этого пользователя создание бота уже начато.")
                self.send_creation_request(pending)
                return True
        return False

    def send_creation_request(self, pending):
        self.say(
            f"Название: {pending['name']}\nUsername: @{pending['username']}\n"
            f"Кому: {self.recipient_label(pending)}\n"
            f"Бюджет: {pending['budget_seconds']} секунд.\n"
            "Подтверди создание в Telegram. Сохрани предложенный @username, "
            "чтобы привязать параметры к боту.",
            reply_markup={
                "keyboard": [
                    [
                        {
                            "text": "Создать в Telegram",
                            "request_managed_bot": {
                                "request_id": secrets.randbelow(2**31),
                                "suggested_name": pending["name"],
                                "suggested_username": pending["username"],
                            },
                        }
                    ]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

    def register(self, bot):
        key = f"bot:{bot['id']}"
        existing = self.repo.get(key)
        username = bot.get("username", "")
        pending_key = f"pending:{username}"
        record = existing or self.repo.get(pending_key)
        if not record:
            self.say(
                f"Получен бот @{username}, но его параметры не найдены. "
                "При создании нужно сохранить предложенный @username."
            )
            return
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
        self.prepare_claim(record)
        self.repo.delete(pending_key)
        self.say(
            "Бот сохранён.\n" + self.describe(record),
            reply_markup=self.share_keyboard(record),
        )

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

    def choose_recipient(self):
        request_id = secrets.randbelow(2**31)
        self.repo.put(
            "draft", {"step": "recipient", "request_id": request_id}
        )
        self.say(
            "Кому? Выбери пользователя в Telegram.",
            reply_markup={
                "keyboard": [
                    [
                        {
                            "text": "Выбрать пользователя",
                            "request_users": {
                                "request_id": request_id,
                                "user_is_bot": False,
                                "max_quantity": 1,
                                "request_username": True,
                                "request_name": True,
                            },
                        }
                    ]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

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

    def claim_bot(self, message, claim_token):
        record = next(
            (
                bot
                for bot in self.repo.list_bots()
                if bot.get("claim_token")
                and secrets.compare_digest(bot["claim_token"], claim_token)
            ),
            None,
        )
        sender = message.get("from", {})
        sender_id = sender.get("id")
        if not record or not isinstance(sender_id, int) or sender_id <= 0:
            self.api.call(
                "sendMessage",
                chat_id=sender_id,
                text="Ссылка недействительна или уже использована.",
            )
            return

        record.update(
            recipient_id=sender_id,
            recipient_username=sender.get("username", ""),
            recipient_name=sender.get("first_name", ""),
        )
        if not self.grant_access(record):
            self.api.call(
                "sendMessage",
                chat_id=sender_id,
                text="Не удалось активировать доступ. Попробуй ещё раз позже.",
            )
            return

        self.api.call(
            "sendMessage",
            chat_id=sender_id,
            text="Готово! Доступ активирован.",
            reply_markup={
                "inline_keyboard": [
                    [
                        {
                            "text": "Открыть моего бота",
                            "url": f"https://t.me/{record['username']}",
                        }
                    ]
                ]
            },
        )

    def claim_bot_from_child(self, record, message, child_api):
        text = (message.get("text") or "").strip()
        parts = text.split(maxsplit=1)
        expected = record.get("claim_token")
        supplied = (
            parts[1][len("claim_") :]
            if len(parts) == 2
            and parts[0].split("@")[0] == "/start"
            and parts[1].startswith("claim_")
            else ""
        )
        sender = message.get("from", {})
        sender_id = sender.get("id")
        if (
            not expected
            or not supplied
            or not isinstance(sender_id, int)
            or sender_id <= 0
            or not secrets.compare_digest(expected, supplied)
        ):
            if isinstance(sender_id, int) and sender_id > 0:
                child_api.call(
                    "sendMessage",
                    chat_id=sender_id,
                    text="Используй персональную ссылку, которую тебе отправили.",
                )
            return False

        record.update(
            recipient_id=sender_id,
            recipient_username=sender.get("username", ""),
            recipient_name=sender.get("first_name", ""),
        )
        if not self.grant_access(record):
            child_api.call(
                "sendMessage",
                chat_id=sender_id,
                text="Не удалось активировать доступ. Попробуй ещё раз позже.",
            )
            return False

        child_api.call(
            "sendMessage",
            chat_id=sender_id,
            text="Готово! Это твой персональный бот.",
        )
        return True

    @staticmethod
    def invitation(bot):
        activation_link = AdminService.activation_link(bot)
        if bot.get("access_status") != "configured" and activation_link:
            return "Ваш персональный бот готов.\n" f"Получить бота: {activation_link}"
        invitation = (
            f"Тебе выделен бот «{bot.get('name') or bot['username']}».\n"
            f"Бюджет: {bot.get('budget_seconds', bot['remaining_seconds'])} секунд видео.\n"
            f"https://t.me/{bot['username']}"
        )
        return invitation

    @staticmethod
    def activation_link(bot):
        username = bot.get("username")
        claim_token = bot.get("claim_token")
        if username and claim_token:
            return f"https://t.me/{username}?start=claim_{claim_token}"
        return None

    @staticmethod
    def share_keyboard(bot):
        invitation = AdminService.invitation(bot)
        return AdminService.recipient_keyboard(bot, invitation)

    @staticmethod
    def recipient_keyboard(bot, invitation):
        recipient = bot.get("recipient_username")
        if recipient:
            url = f"https://t.me/{recipient}?" + urlencode(
                {"text": invitation}, quote_via=quote
            )
            return {
                "inline_keyboard": [
                    [
                        {
                            "text": "Открыть чат с получателем",
                            "url": url,
                        }
                    ]
                ]
            }
        # Telegram supports draft text for username links, not user-ID links.
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "Скопировать приглашение",
                        "copy_text": {"text": invitation},
                    }
                ],
                [
                    {
                        "text": "Открыть профиль получателя",
                        "url": f"tg://user?id={bot['recipient_id']}",
                    }
                ],
            ]
        }

    @staticmethod
    def recipient_label(bot):
        if bot.get("recipient_username"):
            return "@" + bot["recipient_username"]
        return bot.get("recipient_name") or str(bot.get("recipient_id", "не указан"))

    @staticmethod
    def describe(bot):
        return (
            f"https://t.me/{bot['username']}\nКому: {AdminService.recipient_label(bot)}\n"
            f"ID получателя: {bot.get('recipient_id', 'не указан')}\n"
            f"Осталось: {bot['remaining_seconds']} секунд.\n"
            + (
                "Доступ выдан выбранному пользователю и владельцу.\n"
                if bot.get("access_status") == "configured"
                else (
                    "Отправь получателю приглашение. После перехода по ссылке "
                    "и нажатия Start доступ будет выдан автоматически.\n"
                    if bot.get("access_status") == "needs_recipient_start"
                    else "Доступ ещё не настроен.\n"
                )
            )
            + "Бот пустой, обработчики не подключены."
        )


cache_folder = Path(__file__).parent / ".cache"
admin_router = Router()


def process_claim_updates() -> int:
    """Poll unclaimed managed bots until their one-time link is used."""
    settings = get_admin_bot_settings()
    if not settings.token or settings.owner_id <= 0:
        raise RuntimeError("ADMIN_BOT_TOKEN and ADMIN_BOT_OWNER_ID are required")

    cache_folder.mkdir(mode=0o700, exist_ok=True)
    repository = Repository(cache_folder / "admin.sqlite3")
    processed = 0
    try:
        service = AdminService(
            TelegramAPI(settings.token), repository, settings.owner_id
        )
        for record in repository.list_bots():
            if record.get("access_status") != "awaiting_claim" or not record.get(
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
                    service.claim_bot_from_child(record, message, child_api)
                processed += 1
            repository.put(f"bot:{record['bot_id']}", record)
    finally:
        repository.db.close()
    return processed


def process_telegram_update(body: dict) -> None:
    """Run the admin dialogue against a Telegram update."""
    settings = get_admin_bot_settings()
    if not settings.token or settings.owner_id <= 0:
        raise RuntimeError("ADMIN_BOT_TOKEN and ADMIN_BOT_OWNER_ID are required")

    cache_folder.mkdir(mode=0o700, exist_ok=True)
    repository = Repository(cache_folder / "admin.sqlite3")
    try:
        AdminService(TelegramAPI(settings.token), repository, settings.owner_id).handle(
            body
        )
    finally:
        repository.db.close()


@admin_router.message()
async def handle_message(message: Message) -> None:
    await asyncio.to_thread(
        process_telegram_update,
        {"message": message.model_dump(mode="json", by_alias=True, exclude_none=True)},
    )


@admin_router.managed_bot()
async def handle_managed_bot(event: ManagedBotUpdated) -> None:
    await asyncio.to_thread(
        process_telegram_update,
        {
            "managed_bot": event.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
        },
    )
