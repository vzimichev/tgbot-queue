import mimetypes

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message

from bot_factories.faceswap_bot.repository import (
    process_face_fusion_task,
    save_document,
)

faceswap_router = Router()


def extract_media(message: Message) -> tuple[str, str, str] | None:
    """Return media kind, Telegram file id, and a usable filename."""
    if message.document:
        document = message.document
        mime_type = (
            document.mime_type or mimetypes.guess_type(document.file_name or "")[0]
        )
        if mime_type and mime_type.startswith("image/"):
            return "photo", document.file_id, document.file_name or "source.jpg"
        if mime_type and mime_type.startswith("video/"):
            return "video", document.file_id, document.file_name or "target.mp4"
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


async def generate_result(message: Message, state: FSMContext, data: dict) -> None:
    await message.answer("Photo and video received. Generation started...")
    try:
        photo_path = await save_document(
            bot=message.bot,
            file_id=data["photo_file_id"],
            file_name=data["photo_file_name"],
        )
        video_path = await save_document(
            bot=message.bot,
            file_id=data["video_file_id"],
            file_name=data["video_file_name"],
        )
        output_path = await process_face_fusion_task(
            photo_path=photo_path,
            video_path=video_path,
        )
        await message.answer_document(
            FSInputFile(output_path),
            caption="Face swap complete.",
        )
    except Exception:
        await message.answer("Face swap failed. Check the local worker log.")
        raise
    finally:
        await state.clear()


@faceswap_router.message(Command("start"))
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Send one album containing a photo and a video. "
        "Generation will start automatically."
    )


@faceswap_router.message(F.document | F.photo | F.video)
async def receive_media(message: Message, state: FSMContext) -> None:
    media = extract_media(message)
    if media is None:
        await message.answer("The attachment must be an image or a video.")
        return

    kind, file_id, file_name = media
    data = await state.get_data()

    # Telegram delivers a visual album as separate updates sharing media_group_id.
    # Do not combine attachments accidentally left over from an older album.
    media_group_id = message.media_group_id
    if media_group_id and data.get("media_group_id") not in (None, media_group_id):
        await state.clear()
        data = {}

    await state.update_data(
        **{
            "media_group_id": media_group_id or data.get("media_group_id"),
            f"{kind}_file_id": file_id,
            f"{kind}_file_name": file_name,
        }
    )
    data = await state.get_data()

    if "photo_file_id" in data and "video_file_id" in data:
        await generate_result(message, state, data)
        return

    missing = "video" if kind == "photo" else "photo"
    await message.answer(f"{kind.title()} received. Waiting for {missing}...")


@faceswap_router.message()
async def unsupported_message(message: Message) -> None:
    await message.answer("Send one album containing a photo and a video.")
