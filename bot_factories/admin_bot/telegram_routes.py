import asyncio
import secrets

from aiogram import F, Router
from aiogram.client.bot import Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ManagedBotUpdated, Message
from bot_factories.admin_bot.config import admin_bot_settings

from bot_factories.admin_bot.repositories.telegram_cards import (
    main_menu_keyboard,
    managed_bot_creation_card,
    parse_limit_action,
    bot_card_keyboard,
    bot_card_text,
    show_bot_card,
    user_card,
)
from bot_factories.admin_bot.repositories.managed_bots import (
    ManagedBotsRepository,
)


managed_bots_repository = ManagedBotsRepository()


def is_owner(event: Message | CallbackQuery) -> bool:
    user = event.from_user
    message = event if isinstance(event, Message) else event.message
    return bool(
        user
        and message
        and user.id == admin_bot_settings.owner_id
        and message.chat.id == user.id
    )

admin_router = Router()
admin_router.message.filter(is_owner)
admin_router.callback_query.filter(is_owner)


class AdminFlow(StatesGroup):
    """
    choosing_recipient
                ├─(if user's bot found)─> entering_additional_limit
                └─(if not)─> creating_bot -> entering_initial_limit
    """
    choosing_recipient = State()
    creating_bot = State()
    entering_initial_limit = State()
    entering_additional_limit = State()


@admin_router.message(Command("start"))
async def start(message: Message, state: FSMContext) -> None:
    """Reset an interrupted admin dialogue and show its entry action."""
    await state.clear()
    await state.set_state(AdminFlow.choosing_recipient)
    await message.answer(
        "Choose one Telegram user to manage.",
        reply_markup=main_menu_keyboard(),
    )


@admin_router.callback_query(F.data.startswith("limit:"))
async def handle_limit(query: CallbackQuery, state: FSMContext) -> None:
    if query.message is None or query.data is None:
        await query.answer()
        return

    parsed_action = parse_limit_action(query.data)
    if parsed_action is None:
        await query.answer("Invalid limit action.")
        return

    bot_id, seconds_to_add = parsed_action
    if seconds_to_add is None:
        bot = await asyncio.to_thread(
            managed_bots_repository.get_bot,
            bot_id,
        )
        if bot is None:
            await query.answer("Bot not found.")
            return

        await query.answer()
        await state.set_data(bot_id=bot.id)
        await state.set_state(AdminFlow.entering_additional_limit)
        await query.message.answer("Send the number of seconds to add.")
        return

    try:
        bot = await asyncio.to_thread(
            managed_bots_repository.add_limit,
            bot_id,
            seconds_to_add,
        )
    except LookupError:
        await query.answer("Bot not found.")
        return

    await query.answer()
    await show_bot_card(query.message, bot)


@admin_router.message(StateFilter(AdminFlow.choosing_recipient))
async def receive_recipient(message: Message, state: FSMContext) -> None:
    shared = message.users_shared
    if shared is None or len(shared.users) != 1:
        await message.answer("Choose one user.")
        return

    user = shared.users[0]
    existing_bot = await asyncio.to_thread(
        managed_bots_repository.get_by_recipient,
        user.user_id,
    )
    card = user_card(
        user.user_id,
        user.username,
        user.first_name,
        existing_bot,
    )
    if existing_bot is None:
        await state.update_data(
            recipient_id=user.user_id,
            recipient_username=user.username,
            recipient_name=user.first_name,
        )
        await state.set_state(AdminFlow.creating_bot)
    else:
        await state.clear()
    await message.answer(card.text, reply_markup=card.reply_markup)


@admin_router.message(StateFilter(AdminFlow.creating_bot), F.text == "Create bot")
async def begin_creation(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminFlow.entering_initial_limit)
    await message.answer("Send the initial limit in seconds.")


@admin_router.message(StateFilter(AdminFlow.entering_initial_limit))
async def receive_initial_limit(message: Message, state: FSMContext) -> None:
    seconds = _parse_seconds(message.text)
    if seconds is None:
        await message.answer("Send a positive whole number of seconds.")
        return

    data = await state.get_data()
    recipient_id = data.get("recipient_id")
    if not isinstance(recipient_id, int):
        await state.clear()
        await message.answer("The user selection expired. Start again.")
        return

    try:
        bot = await asyncio.to_thread(
            managed_bots_repository.create_pending_bot,
            recipient_id,
            data.get("recipient_username"),
            data.get("recipient_name"),
            seconds,
        )
    except ValueError:
        await state.clear()
        await message.answer("This user already has a bot. Start again.")
        return

    await state.clear()
    card = managed_bot_creation_card(bot, secrets.randbelow(2**31))
    await message.answer(card.text, reply_markup=card.reply_markup)


@admin_router.message(StateFilter(AdminFlow.entering_additional_limit))
async def receive_additional_limit(message: Message, state: FSMContext) -> None:
    seconds = _parse_seconds(message.text)
    if seconds is None:
        await message.answer("Send a positive whole number of seconds.")
        return

    data = await state.get_data()
    bot_id = data.get("bot_id")
    if not isinstance(bot_id, int):
        await state.clear()
        await message.answer("No bot is selected. Start again.")
        return

    try:
        bot = await asyncio.to_thread(
            managed_bots_repository.add_limit,
            bot_id,
            seconds,
        )
    except LookupError:
        await state.clear()
        await message.answer("Bot not found. Start again.")
        return

    await state.clear()
    await show_bot_card(message, bot)


@admin_router.managed_bot()
async def register_managed_bot(event: ManagedBotUpdated, bot: Bot) -> None:
    """Bind Telegram's creation result to the saved pending record."""
    if event.user.id != admin_bot_settings.owner_id:
        return

    created = event.bot_user
    try:
        record = await asyncio.to_thread(
            managed_bots_repository.register_created_bot,
            created.id,
            created.username or "",
            created.first_name or created.username or "",
        )
    except (RuntimeError, ValueError):
        await bot.send_message(
            event.user.id,
            "The managed bot could not be registered. Please try again.",
        )
        return

    if record is None:
        await bot.send_message(
            event.user.id,
            "This bot does not match a pending creation request.",
        )
        return

    await bot.send_message(
        event.user.id,
        bot_card_text(record),
        reply_markup=bot_card_keyboard(record),
    )


def _parse_seconds(text: str | None) -> int | None:
    value = (text or "").strip()
    if not value.isascii() or not value.isdecimal():
        return None
    seconds = int(value)
    return seconds if seconds > 0 else None
