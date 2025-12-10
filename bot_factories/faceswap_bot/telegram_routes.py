"""
Face Swap Router (Example Implementation)

This router implements a guided flow for uploading a photo and a video in a Telegram chat,
and then scheduling a background task to generate a processed result (e.g., face fusion).

States (FSM):

1. UploadMediaState.waiting_photo
   - User is expected to send a photo as a document (not compressed).
   - If a wrong file type is sent, the bot prompts again.

2. UploadMediaState.waiting_video
   - After a valid photo, user sends a video as a document.
   - Wrong file types are rejected with a prompt.

3. UploadMediaState.ready_to_generate
   - Both photo and video are received.
   - User can send the /generate command to schedule processing.

Result:

- Once /generate is received, the photo and video paths are sent to a background Celery task.
- The task handles heavy processing (e.g., face fusion) without blocking the bot.
- The bot confirms that generation is scheduled and resets the state.

Note:

- This is an example of a workflow-specific router and is **not tied to a specific processing backend**.
- It demonstrates how to structure a multi-step upload flow with FSM, Telegram messages,
  and asynchronous task scheduling.
"""

from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot_factories.faceswap_bot.repository import (process_face_fusion_task,
                                                   save_document)

faceswap_router = Router()


class UploadMediaState(StatesGroup):
    waiting_photo = State()
    waiting_video = State()
    ready_to_generate = State()


@faceswap_router.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    await msg.answer("Send a photo as a document (not compressed).")
    await state.set_state(UploadMediaState.waiting_photo)


@faceswap_router.message(UploadMediaState.waiting_photo, F.document)
async def receive_photo(msg: Message, state: FSMContext):
    await state.update_data(
        photo_file_id=msg.document.file_id, photo_file_name=msg.document.file_name
    )

    await msg.answer("Photo received.\nNow send a video as a document.")
    await state.set_state(UploadMediaState.waiting_video)


@faceswap_router.message(UploadMediaState.waiting_photo)
async def wrong_photo(msg: Message):
    await msg.answer("Please send a photo as document. No images/stickers/etc.")


@faceswap_router.message(UploadMediaState.waiting_video, F.document)
async def receive_video(msg: Message, state: FSMContext):
    await state.update_data(
        video_file_id=msg.document.file_id, video_file_name=msg.document.file_name
    )

    await msg.answer("Video received.\nSend /generate to produce the result.")
    await state.set_state(UploadMediaState.ready_to_generate)


@faceswap_router.message(UploadMediaState.waiting_video)
async def wrong_video(msg: Message):
    await msg.answer("Please send a video as document.")


@faceswap_router.message(UploadMediaState.ready_to_generate, Command("generate"))
async def generate(msg: Message, state: FSMContext):
    data = await state.get_data()

    photo_file_id = data["photo_file_id"]
    photo_file_name = data["photo_file_name"]
    photo_path = await save_document(
        bot=msg.bot,
        file_id=photo_file_id,
        file_name=photo_file_name,
    )
    await msg.answer("Photo downloaded")

    video_file_id = data["video_file_id"]
    video_file_name = data["video_file_name"]
    video_path = await save_document(
        bot=msg.bot,
        file_id=video_file_id,
        file_name=video_file_name,
    )
    await msg.answer("Video downloaded")

    await msg.answer("Generation started...")
    await process_face_fusion_task(
        photo_path=photo_path,
        video_path=video_path,
    )
    await state.clear()


@faceswap_router.message(UploadMediaState.ready_to_generate)
async def waiting_generate(msg: Message):
    await msg.answer("Send /generate to start.")


@faceswap_router.message()
async def command_start_handler(msg: Message) -> None:
    await msg.answer("Press /start")
