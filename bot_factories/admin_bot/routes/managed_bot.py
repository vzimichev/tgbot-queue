import asyncio
import mimetypes

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from celery import current_app

from bot_factories.admin_bot.job_names import FACESWAP_QUEUE, MANAGED_FACESWAP_TASK
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


class ManagedFaceSwapFlow(StatesGroup):
    WAITING_FOR_MEDIA = State()


def extract_media(message: Message) -> tuple[str, str, str] | None:
    """Return media kind, Telegram file id, and a safe fallback filename."""
    if message.document:
        document = message.document
        mime_type = (
            document.mime_type or mimetypes.guess_type(document.file_name or "")[0]
        )
        if mime_type and mime_type.startswith("image/"):
            return "photo", document.file_id, document.file_name or "source.jpg"
        return None
    if message.photo:
        photo = message.photo[-1]
        return "photo", photo.file_id, f"source-{photo.file_unique_id}.jpg"
    if message.video:
        video = message.video
        return (
            "video",
            video.file_id,
            video.file_name or f"target-{video.file_unique_id}.mp4",
        )
    return None


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


@managed_bot_router.message(Command("faceswap"))
async def begin_managed_faceswap(
    message: Message, state: FSMContext, managed_bot_id: int
) -> dict[str, str]:
    """Start a FaceSwap request for the managed bot's recipient."""
    account = await _recipient_account_for_message(message, managed_bot_id)
    if account is None:
        return {"status": "unavailable"}
    await state.clear()
    await state.set_state(ManagedFaceSwapFlow.WAITING_FOR_MEDIA)
    await message.answer(
        "Send one photo and one video (separately or in the same album). "
        "The video duration will be deducted from your remaining limit."
    )
    return {"status": "awaiting_media"}


@managed_bot_router.message(
    StateFilter(ManagedFaceSwapFlow.WAITING_FOR_MEDIA), F.document | F.photo | F.video
)
async def receive_managed_faceswap_media(
    message: Message, state: FSMContext, managed_bot_id: int, managed_update_id: int
) -> dict[str, str]:
    account = await _recipient_account_for_message(message, managed_bot_id)
    if account is None:
        await state.clear()
        return {"status": "unavailable"}
    media = extract_media(message)
    if media is None:
        await message.answer("The attachment must be an image or a video.")
        return {"status": "unsupported_media"}

    kind, file_id, file_name = media
    data = await state.get_data()
    media_group_id = message.media_group_id
    if media_group_id and data.get("media_group_id") not in (None, media_group_id):
        await state.clear()
        data = {}
    await state.update_data(
        **{
            "media_group_id": media_group_id or data.get("media_group_id"),
            f"{kind}_file_id": file_id,
            f"{kind}_file_name": file_name,
            **(
                {"video_duration": message.video.duration}
                if kind == "video" and message.video
                else {}
            ),
        }
    )
    data = await state.get_data()
    if "photo_file_id" not in data or "video_file_id" not in data:
        missing = "video" if kind == "photo" else "photo"
        await message.answer(f"{kind.title()} received. Waiting for {missing}...")
        return {"status": "awaiting_media"}

    duration = int(data["video_duration"])
    charge = await asyncio.to_thread(
        managed_bot_transactions_repository.charge_video,
        managed_bot_id,
        message.from_user.id,
        managed_update_id,
        duration,
    )
    if charge.result == ManagedBotVideoChargeResult.INSUFFICIENT:
        await message.answer(
            f"This video is {duration} seconds, but only "
            f"{charge.remaining_seconds} seconds remain. "
            "Ask the administrator to add more time."
        )
        return {"status": charge.result.value}
    if charge.result == ManagedBotVideoChargeResult.DUPLICATE:
        return {"status": charge.result.value}
    if charge.result != ManagedBotVideoChargeResult.CONSUMED:
        await state.clear()
        return {"status": charge.result.value}

    current_app.send_task(
        MANAGED_FACESWAP_TASK,
        args=[message.bot.token, message.chat.id, data],
        queue=FACESWAP_QUEUE,
    )
    await state.clear()
    await message.answer("Face swap task queued.")
    return {"status": "queued"}


@managed_bot_router.message(StateFilter(ManagedFaceSwapFlow.WAITING_FOR_MEDIA))
async def managed_faceswap_needs_media(message: Message) -> dict[str, str]:
    await message.answer("Send a photo or video, or use /faceswap to restart.")
    return {"status": "awaiting_media"}


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
