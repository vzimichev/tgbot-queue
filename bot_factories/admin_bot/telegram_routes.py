import asyncio
import secrets
from urllib.parse import quote, urlencode

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ManagedBotUpdated

from bot_factories.admin_bot.config import get_admin_bot_settings
from bot_factories.admin_bot.repository import run_bot_operation

admin_router = Router()


class Creation(StatesGroup):
    recipient = State()
    seconds = State()
    add_limit = State()


class Owner(Filter):
    async def __call__(self, message: Message):
        owner = get_admin_bot_settings().owner_id
        return bool(
            message.from_user
            and message.from_user.id == owner
            and message.chat.id == owner
        )


async def operation(callback):
    return await asyncio.to_thread(run_bot_operation, callback)


async def answer(message, text, reply_markup=None):
    await message.answer(text, reply_markup=reply_markup, parse_mode=None)


def main_keyboard():
    return {
        "keyboard": [
            [{"text": "Создать бота / добавить лимит"}],
            [{"text": "Мои боты"}, {"text": "Отмена"}],
        ],
        "resize_keyboard": True,
    }


def cancel_keyboard():
    return {"keyboard": [[{"text": "Отмена"}]], "resize_keyboard": True}


def invitation(bot):
    link = activation_link(bot)
    if bot.get("access_status") != "configured" and link:
        return "Ваш персональный бот готов.\n" f"Получить бота: {link}"
    invitation = (
        f"Тебе выделен бот «{bot.get('name') or bot['username']}».\n"
        f"Бюджет: {bot.get('budget_seconds', bot['remaining_seconds'])} секунд видео.\n"
        f"https://t.me/{bot['username']}"
    )
    return invitation


def activation_link(bot):
    username = bot.get("username")
    claim_token = bot.get("claim_token")
    if username and claim_token:
        return f"https://t.me/{username}?start=claim_{claim_token}"
    return None


def share_keyboard(bot):
    return recipient_keyboard(bot, invitation(bot))


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


def recipient_label(bot):
    if bot.get("recipient_username"):
        return "@" + bot["recipient_username"]
    return bot.get("recipient_name") or str(bot.get("recipient_id", "не указан"))


def describe(bot):
    return (
        f"https://t.me/{bot['username']}\nКому: {recipient_label(bot)}\n"
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


async def send_creation_request(message, pending):
    await answer(
        message,
        f"Название: {pending['name']}\nUsername: @{pending['username']}\n"
        f"Кому: {recipient_label(pending)}\n"
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
                ],
                [{"text": "Отмена"}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
    )


@admin_router.message(Command("start"), F.chat.type == "private")
async def start(message: Message, state: FSMContext, command: CommandObject):
    if message.from_user.id == get_admin_bot_settings().owner_id:
        await show_menu(message, state)
        return
    if command.args and command.args.startswith("claim_"):
        token = command.args[len("claim_") :]
        sender = message.from_user.model_dump(exclude_none=True)

        def activate(bots):
            record = bots.find_claim(token)
            return record, bots.activate_claim(record, sender, token)

        record, result = await operation(activate)
        if result == "invalid":
            await answer(message, "Ссылка недействительна или уже использована.")
        elif result == "failed":
            await answer(
                message, "Не удалось активировать доступ. Попробуй ещё раз позже."
            )
        else:
            await answer(
                message,
                "Готово! Доступ активирован.",
                open_bot_keyboard(record, "Открыть моего бота"),
            )
        return
    records = await operation(lambda bots: bots.repo.list_bots())
    assigned = [
        record
        for record in records
        if record.get("recipient_id") == message.from_user.id
    ]
    for record in assigned:
        if await operation(lambda bots: bots.grant_access(record)):
            await answer(
                message,
                invitation(record),
                open_bot_keyboard(record, "Открыть своего бота"),
            )
        else:
            await answer(
                message,
                "Доступ пока не удалось настроить. Открой бота по ссылке ещё раз.",
            )
    if records and not assigned:
        await answer(
            message,
            "Этот аккаунт не назначен получателем бота. "
            f"Твой Telegram ID: {message.from_user.id}. "
            "Передай его владельцу, чтобы он проверил выбор пользователя.",
        )


def open_bot_keyboard(record, text):
    return {
        "inline_keyboard": [
            [{"text": text, "url": f"https://t.me/{record['username']}"}]
        ]
    }


async def show_menu(message: Message, state: FSMContext):
    await state.clear()
    await answer(
        message,
        "Выбери действие с помощью кнопок ниже.\n"
        "Бюджет задаётся в секундах и не списывается.",
        main_keyboard(),
    )


@admin_router.message(Owner(), F.text == "Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await answer(message, "Ввод отменён.", main_keyboard())


@admin_router.message(Owner(), F.text == "Мои боты")
async def list_bots(message: Message, state: FSMContext):
    records = await operation(lambda bots: bots.repo.list_bots())
    if not records:
        await answer(
            message,
            "Пока нет созданных ботов.",
            cancel_keyboard() if await state.get_state() else main_keyboard(),
        )
    for record in records:
        await answer(message, describe(record), share_keyboard(record))


@admin_router.message(
    Owner(), F.text.in_({"Создать бота", "Создать бота / добавить лимит"})
)
async def create(message: Message, state: FSMContext):
    await state.clear()
    request_id = secrets.randbelow(2**31)
    await state.set_data({"request_id": request_id})
    await state.set_state(Creation.recipient)
    await answer(
        message,
        "Кому? Выбери пользователя в Telegram.",
        {
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
                ],
                [{"text": "Отмена"}],
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
    )


@admin_router.message(Owner(), F.users_shared)
async def select_recipient(message: Message, state: FSMContext):
    data = await state.get_data()
    shared = message.users_shared
    if (
        await state.get_state() != Creation.recipient.state
        or shared.request_id != data.get("request_id")
    ):
        await answer(
            message,
            "Этот выбор устарел. Нажми «Создать бота / добавить лимит», чтобы начать заново.",
            main_keyboard(),
        )
        return
    if len(shared.users) != 1 or shared.users[0].user_id <= 0:
        await answer(message, "Выбери одного пользователя.", cancel_keyboard())
        return
    user = shared.users[0]
    recipient = {
        "recipient_id": user.user_id,
        "recipient_username": user.username or "",
        "recipient_name": user.first_name or "",
    }
    existing, pending = await operation(lambda bots: bots.find_recipient(user.user_id))
    if existing or pending:
        key = (
            f"bot:{existing['bot_id']}"
            if existing
            else f"pending:{pending['username']}"
        )
        await state.set_data({"key": key})
        await state.set_state(Creation.add_limit)
        text = "Бот уже создан." if existing else "Создание бота уже начато."
        await answer(
            message, text + " Сколько секунд добавить к лимиту?", cancel_keyboard()
        )
    else:
        await state.set_data(recipient)
        await state.set_state(Creation.seconds)
        await answer(
            message,
            "Как долго? Отправь бюджет в секундах, например 600.",
            cancel_keyboard(),
        )


@admin_router.message(Owner(), F.managed_bot_created)
async def creation_notice(message: Message):
    # Registration arrives in a separate managed_bot update.
    pass


@admin_router.message(Owner(), Creation.seconds)
@admin_router.message(Owner(), Creation.add_limit)
async def budget(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text.isascii() or not text.isdecimal() or not 0 < int(text) <= 2**52:
        await answer(
            message, "Введи положительное целое число секунд.", cancel_keyboard()
        )
        return
    data = await state.get_data()
    if await state.get_state() == Creation.add_limit.state:
        try:
            record = await operation(
                lambda bots: bots.add_limit(data["key"], int(text))
            )
        except LookupError:
            await state.clear()
            await answer(
                message,
                "Бот не найден. Нажми «Создать бота / добавить лимит», чтобы начать заново.",
                main_keyboard(),
            )
            return
        except ValueError:
            await answer(message, "Итоговый лимит слишком велик.", cancel_keyboard())
            return
        await state.clear()
        await answer(
            message,
            f"Добавлено {int(text)} секунд. Новый лимит: {record['remaining_seconds']} секунд.",
            main_keyboard(),
        )
        if data["key"].startswith("pending:"):
            await send_creation_request(message, record)
        return
    existing, pending = await operation(
        lambda bots: bots.find_recipient(data["recipient_id"])
    )
    if existing:
        await state.clear()
        await answer(message, "Для этого пользователя бот уже создан.", main_keyboard())
        await answer(message, describe(existing), share_keyboard(existing))
        return
    if pending is None:
        pending = await operation(lambda bots: bots.create_pending(data, int(text)))
    await state.clear()
    await send_creation_request(message, pending)


@admin_router.message(Owner(), Creation.recipient)
async def waiting_for_recipient(message: Message):
    await answer(message, "Нажми кнопку «Выбрать пользователя».")


@admin_router.message(Owner())
async def unsupported_message(message: Message):
    await answer(message, "Выбери действие с помощью кнопок ниже.", main_keyboard())


@admin_router.managed_bot()
async def register_bot(event: ManagedBotUpdated, bot):
    owner = get_admin_bot_settings().owner_id
    if event.user.id != owner:
        return
    record = await operation(
        lambda bots: bots.register(event.bot_user.model_dump(exclude_none=True))
    )
    if record is None:
        await bot.send_message(
            owner,
            f"Получен бот @{event.bot_user.username or ''}, но его параметры не найдены. "
            "При создании нужно сохранить предложенный @username.",
            reply_markup=main_keyboard(),
            parse_mode=None,
        )
        return
    await bot.send_message(
        owner, "Бот сохранён.", reply_markup=main_keyboard(), parse_mode=None
    )
    await bot.send_message(
        owner, describe(record), reply_markup=share_keyboard(record), parse_mode=None
    )


def notify_child_claim(message, child_api, result):
    sender_id = message.get("from", {}).get("id")
    if not isinstance(sender_id, int) or sender_id <= 0:
        return
    text = {
        "invalid": "Используй персональную ссылку, которую тебе отправили.",
        "failed": "Не удалось активировать доступ. Попробуй ещё раз позже.",
        "configured": "Готово! Это твой персональный бот.",
    }[result]
    child_api.call("sendMessage", chat_id=sender_id, text=text)
