from urllib.parse import quote, urlencode

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestManagedBot,
    KeyboardButtonRequestUsers,
    Message,
    ReplyKeyboardMarkup,
)
from dataclasses import dataclass

from bot_factories.admin_bot.db.managed_bots import ManagedBotRow, ManagedBotStatus
from bot_factories.admin_bot.repositories.bot_activation import (
    ManagedBotActivationService,
)

LIMIT_PRESETS_SECONDS = (10, 100, 1000)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Return the entry keyboard for the admin dialogue."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Choose user",
                    request_users=KeyboardButtonRequestUsers(
                        request_id=1,
                        user_is_bot=False,
                        max_quantity=1,
                        request_username=True,
                        request_name=True,
                    ),
                )
            ],
            [KeyboardButton(text="All bots")],
        ],
        resize_keyboard=True,
    )


@dataclass(frozen=True)
class UserCard:
    text: str
    reply_markup: ReplyKeyboardMarkup | InlineKeyboardMarkup | None = None


def user_card(
    recipient_id: int,
    recipient_username: str | None,
    recipient_name: str | None,
    bot: ManagedBotRow | None,
) -> UserCard:
    recipient = (
        f"@{recipient_username}"
        if recipient_username
        else recipient_name or str(recipient_id)
    )
    if bot is None:
        return UserCard(
            text=f"User: {recipient}\nNo bot yet.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Create bot")],
                    [KeyboardButton(text="Back")],
                ],
                resize_keyboard=True,
            ),
        )

    status_text = {
        ManagedBotStatus.PENDING_CREATION: "Creation pending.",
        ManagedBotStatus.AWAITING_ACTIVATION: "Awaiting activation.",
        ManagedBotStatus.ACTIVE: "Active.",
        ManagedBotStatus.ERROR: "Bot setup failed.",
    }[bot.status]
    return UserCard(
        text=(
            f"User: {recipient}\n"
            f"Bot: @{bot.username}\n"
            f"{status_text}\n"
            f"Remaining: {bot.remaining_seconds} seconds"
        ),
        reply_markup=bot_card_keyboard(bot),
    )


def managed_bot_creation_card(bot: ManagedBotRow, request_id: int) -> UserCard:
    """Return Telegram's native managed-bot creation action for a pending bot."""
    return UserCard(
        text=(
            f"Create @{bot.username} in Telegram.\n"
            f"Initial limit: {bot.remaining_seconds} seconds."
        ),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="Create in Telegram",
                        request_managed_bot=KeyboardButtonRequestManagedBot(
                            request_id=request_id,
                            suggested_name=bot.name,
                            suggested_username=bot.username,
                        ),
                    )
                ],
                [KeyboardButton(text="Back")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


def parse_limit_action(
    callback_data: str | None,
) -> tuple[int, int | None] | None:
    if callback_data is None:
        return None

    prefix, separator, payload = callback_data.partition(":")
    if prefix != "limit" or not separator:
        return None

    bot_id_text, separator, amount_text = payload.partition(":")
    if not separator or not bot_id_text.isdecimal():
        return None

    if amount_text == "custom":
        return int(bot_id_text), None
    if amount_text not in {str(seconds) for seconds in LIMIT_PRESETS_SECONDS}:
        return None
    return int(bot_id_text), int(amount_text)


def bot_card_text(bot: ManagedBotRow) -> str:
    recipient = (
        f"@{bot.recipient_username}"
        if bot.recipient_username
        else bot.recipient_name or str(bot.recipient_id)
    )
    status = {
        ManagedBotStatus.PENDING_CREATION: "Pending creation",
        ManagedBotStatus.AWAITING_ACTIVATION: "Awaiting activation",
        ManagedBotStatus.ACTIVE: "Active",
        ManagedBotStatus.ERROR: "Error",
    }[bot.status]
    return (
        f"Recipient: {recipient}\n"
        f"Bot: @{bot.username}\n"
        f"Status: {status}\n"
        f"Remaining: {bot.remaining_seconds} seconds"
    )


def bot_link(bot: ManagedBotRow) -> str:
    activation_link = ManagedBotActivationService.activation_link(bot)
    if bot.status != ManagedBotStatus.ACTIVE and activation_link:
        return activation_link
    return f"https://t.me/{bot.username}"


def invitation_text(bot: ManagedBotRow, link: str) -> str:
    if bot.status != ManagedBotStatus.ACTIVE:
        return (
            "Your personal bot is ready.\n"
            f"Limit: {bot.remaining_seconds} seconds.\n"
            f"Get your bot: {link}"
        )
    return (
        f"You have been assigned the bot “{bot.name or bot.username}”.\n"
        f"Remaining limit: {bot.remaining_seconds} seconds.\n"
        f"{link}"
    )


def invitation_button(bot: ManagedBotRow) -> InlineKeyboardButton:
    link = bot_link(bot)
    text = invitation_text(bot, link)
    if bot.recipient_username:
        username = bot.recipient_username.lstrip("@")
        return InlineKeyboardButton(
            text="Send to recipient",
            url=f"https://t.me/{username}?"
            + urlencode({"text": text}, quote_via=quote),
        )
    return InlineKeyboardButton(
        text="Share link",
        url="https://t.me/share/url?"
        + urlencode(
            {"url": link, "text": text.replace(link, "").strip()},
            quote_via=quote,
        ),
    )


def bot_card_keyboard(bot: ManagedBotRow) -> InlineKeyboardMarkup:
    rows = []
    if bot.telegram_bot_id is not None:
        rows.append([invitation_button(bot)])
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=f"+{seconds}",
                    callback_data=f"limit:{bot.id}:{seconds}",
                )
                for seconds in LIMIT_PRESETS_SECONDS
            ],
            [
                InlineKeyboardButton(
                    text="Custom amount", callback_data=f"limit:{bot.id}:custom"
                )
            ],
            [InlineKeyboardButton(text="Back", callback_data="menu:back")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Back")]],
        resize_keyboard=True,
    )


async def show_bot_card(message: Message, bot: ManagedBotRow) -> None:
    await message.answer(bot_card_text(bot), reply_markup=bot_card_keyboard(bot))
