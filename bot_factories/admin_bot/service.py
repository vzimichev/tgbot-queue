import secrets
from urllib.parse import quote, urlencode


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
        if (
            message.get("from", {}).get("id") != self.owner
            or message.get("chat", {}).get("id") != self.owner
        ):
            return
        if message.get("users_shared"):
            shared = message["users_shared"]
            draft = self.repo.get("draft")
            if (
                not draft
                or draft.get("step") != "recipient"
                or shared.get("request_id") != draft.get("request_id")
            ):
                self.say("Этот выбор устарел. Начни заново через /create или /access.")
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
            if self.recipient_taken(recipient["recipient_id"], draft.get("bot_id")):
                self.repo.delete("draft")
                return
            if draft.get("bot_id"):
                record = self.repo.get(f"bot:{draft['bot_id']}")
                record.update(recipient)
                self.repo.put(f"bot:{draft['bot_id']}", record)
                self.grant_access(record)
                self.say(
                    "Доступ настроен.\n" + self.describe(record),
                    reply_markup=self.share_keyboard(record),
                )
                self.repo.delete("draft")
            else:
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
                "/create — создать бота\n/bots — список ботов\n"
                "/access <ID бота> — назначить доступ существующему боту\n"
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
        elif command == "/access":
            parts = text.split()
            if (
                len(parts) != 2
                or not parts[1].isascii()
                or not parts[1].isdigit()
                or not self.repo.get(f"bot:{int(parts[1])}")
            ):
                self.say("Укажи ID сохранённого бота: /access <ID>. Список: /bots.")
                return
            self.choose_recipient(bot_id=int(parts[1]))
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
                    "name": f"Personal {secrets.token_hex(3)}",
                }
                self.repo.put(f"pending:{username}", pending)
                self.send_creation_request(pending)
                self.repo.delete("draft")

    def recipient_taken(self, recipient_id, current_bot_id=None):
        for bot in self.repo.list_bots():
            if bot.get("recipient_id") == recipient_id and (
                current_bot_id is None or bot.get("bot_id") != current_bot_id
            ):
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
        }
        self.repo.put(key, record)
        self.grant_access(record)
        self.repo.delete(pending_key)
        self.say(
            "Бот сохранён.\n" + self.describe(record),
            reply_markup=self.share_keyboard(record),
        )

    def choose_recipient(self, bot_id=None):
        request_id = secrets.randbelow(2**31)
        self.repo.put(
            "draft", {"step": "recipient", "request_id": request_id, "bot_id": bot_id}
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
            self.repo.put(f"bot:{record['bot_id']}", record)
            return
        self.api.call(
            "setManagedBotAccessSettings",
            user_id=record["bot_id"],
            is_access_restricted=True,
            added_user_ids=[record["recipient_id"]],
        )
        record["access_status"] = "configured"
        self.repo.put(f"bot:{record['bot_id']}", record)

    @staticmethod
    def share_keyboard(bot):
        if bot.get("access_status") != "configured":
            return {"remove_keyboard": True}
        invitation = (
            f"Тебе выделен бот «{bot.get('name') or bot['username']}».\n"
            f"Бюджет: {bot.get('budget_seconds', bot['remaining_seconds'])} секунд видео."
        )
        invitation += f"\nhttps://t.me/{bot['username']}"
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
            f"Осталось: {bot['remaining_seconds']} секунд.\n"
            + (
                "Доступ выдан выбранному пользователю и владельцу.\n"
                if bot.get("access_status") == "configured"
                else "Доступ ещё не настроен.\n"
            )
            + f"Назначить доступ: /access {bot.get('bot_id', '')}\n"
            + "Бот пустой, обработчики не подключены."
        )
