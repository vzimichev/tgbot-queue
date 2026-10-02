from urllib.parse import quote, urlencode

from aiogram.types import (
    KeyboardButton,
    KeyboardButtonRequestUsers,
    Message,
    ReplyKeyboardMarkup,
)

from bot_factories.admin_bot.db.managed_bots import ManagedBotRow, ManagedBotStatus


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
            ]
        ],
        resize_keyboard=True,
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


def bot_card_keyboard(bot: ManagedBotRow) -> dict:
    rows = []
    if bot.telegram_bot_id is not None:
        invitation = f"https://t.me/{bot.username}"
        rows.append(
            [
                {
                    "text": "Invite",
                    "url": "https://t.me/share/url?"
                    + urlencode({"url": invitation}, quote_via=quote),
                }
            ]
        )
    rows.extend(
        [
            [
                {"text": "+10", "callback_data": f"limit:{bot.id}:10"},
                {"text": "+100", "callback_data": f"limit:{bot.id}:100"},
                {"text": "+1000", "callback_data": f"limit:{bot.id}:1000"},
            ],
            [
                {
                    "text": "Custom amount",
                    "callback_data": f"limit:{bot.id}:custom",
                }
            ],
        ]
    )
    return {"inline_keyboard": rows}


async def show_bot_card(message: Message, bot: ManagedBotRow) -> None:
    await message.answer(bot_card_text(bot), reply_markup=bot_card_keyboard(bot))
