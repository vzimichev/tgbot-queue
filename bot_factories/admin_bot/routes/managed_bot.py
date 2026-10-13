import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot_factories.admin_bot.repositories.bot_manager import ManagedBotAccountResult
from bot_factories.admin_bot.repositories.managed_bot_transactions import (
    ManagedBotVideoChargeResult,
)
from bot_factories.admin_bot.db.managed_bot_transactions import TransactionType
from bot_factories.admin_bot.dependencies import (
    activation_service,
    managed_bot_transactions_repository,
    managed_bots_repository,
)

managed_bot_router = Router()


@managed_bot_router.message(Command("balance"))
async def show_managed_bot_balance(
    message: Message, managed_bot_id: int
) -> dict[str, str]:
    """Show the recipient the remaining video-time allowance."""
    account = await _recipient_account_for_message(message, managed_bot_id)
    if account is None:
        return {"status": "unavailable"}
    await message.answer(f"Remaining limit: {account.remaining_seconds} seconds.")
    return {"status": "balance"}


@managed_bot_router.message(Command("transactions"))
async def show_managed_bot_transactions(
    message: Message, managed_bot_id: int
) -> dict[str, str]:
    """Show up to the 20 latest ledger entries to the bot recipient."""
    account = await _recipient_account_for_message(message, managed_bot_id)
    if account is None:
        return {"status": "unavailable"}

    type_labels = {
        TransactionType.OPENING_BALANCE: "Initial limit",
        TransactionType.TOP_UP: "Limit added",
        TransactionType.VIDEO_DEBIT: "Video processed",
    }
    entries = "\n".join(
        f"• {transaction.created_at:%Y-%m-%d %H:%M} — "
        f"{type_labels[transaction.transaction_type]}: "
        f"{transaction.seconds:+d} seconds"
        for transaction in account.transactions
    )
    await message.answer(
        f"Transactions (latest {len(account.transactions)}):\n{entries}\n\n"
        f"Remaining limit: {account.remaining_seconds} seconds."
    )
    return {"status": "transactions"}


@managed_bot_router.message()
async def process_managed_bot_message(
    message: Message,
    managed_bot_id: int,
    managed_update_id: int,
) -> dict[str, str]:
    if message.from_user is None:
        return {"status": "ignored"}

    if getattr(message, "video", None) is not None:
        charge = await asyncio.to_thread(
            managed_bot_transactions_repository.charge_video,
            managed_bot_id,
            message.from_user.id,
            managed_update_id,
            message.video.duration,
        )
        if charge.result == ManagedBotVideoChargeResult.FORBIDDEN:
            await message.answer(
                "This personal bot is available only to its recipient."
            )
        elif charge.result == ManagedBotVideoChargeResult.CONSUMED:
            await message.answer(
                f"Video accepted: {message.video.duration} seconds charged. "
                f"Remaining limit: {charge.remaining_seconds} seconds."
            )
        elif charge.result == ManagedBotVideoChargeResult.INSUFFICIENT:
            await message.answer(
                f"This video is {message.video.duration} seconds, but only "
                f"{charge.remaining_seconds} seconds remain. "
                "Ask the administrator to add more time."
            )
        return {"status": charge.result.value}

    result = await asyncio.to_thread(
        activation_service.handle_claim,
        telegram_bot_id=managed_bot_id,
        update_id=managed_update_id,
        command_text=message.text,
        claimant_id=message.from_user.id,
        claimant_username=message.from_user.username,
        claimant_name=message.from_user.first_name,
    )
    texts = {
        "configured": "Access activated. You can now use your personal bot.",
        "invalid": "Use the personal activation link that was sent to you.",
        "failed": "Access could not be activated. Please try the link again later.",
        "blocked": "Activation could not be completed. Contact the administrator.",
    }
    text = texts.get(result.value)
    if text:
        await message.answer(text)
    return {"status": result.value}


async def _recipient_account_for_message(message: Message, managed_bot_id: int):
    if message.from_user is None:
        return None
    account = await asyncio.to_thread(
        managed_bots_repository.get_managed_bot_account,
        managed_bot_id,
        message.from_user.id,
    )
    if account.result == ManagedBotAccountResult.FORBIDDEN:
        await message.answer("This personal bot is available only to its recipient.")
        return None
    if account.result == ManagedBotAccountResult.INACTIVE:
        await message.answer(
            "Access has not been activated yet. Use your activation link."
        )
        return None
    return account
