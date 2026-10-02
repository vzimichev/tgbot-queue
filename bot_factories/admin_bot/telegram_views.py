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

from bot_factories.admin_bot.crud import ManagedBotRow, ManagedBotStatus


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
                ]
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
    if amount_text not in {"10", "100", "1000"}:
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


def bot_card_keyboard(bot: ManagedBotRow) -> InlineKeyboardMarkup:
    rows = []
    if bot.telegram_bot_id is not None:
        invitation = f"https://t.me/{bot.username}"
        rows.append(
            [
                InlineKeyboardButton(
                    text="Invite",
                    url="https://t.me/share/url?"
                    + urlencode({"url": invitation}, quote_via=quote),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(text="+10", callback_data=f"limit:{bot.id}:10"),
                InlineKeyboardButton(text="+100", callback_data=f"limit:{bot.id}:100"),
                InlineKeyboardButton(
                    text="+1000", callback_data=f"limit:{bot.id}:1000"
                ),
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
