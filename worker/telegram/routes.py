from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Document, Message

from worker import tasks
from worker.telegram.bot import bot
from worker.telegram.states import UploadMediaState

cache_folder = Path(__file__).parent.parent / ".cache"
router = Router()


@router.message(Command("start"))
async def start(msg: Message, state: FSMContext):
    await msg.answer("Send a photo as a document (not compressed).")
    await state.set_state(UploadMediaState.waiting_photo)


@router.message(UploadMediaState.waiting_photo, F.document)
async def receive_photo(msg: Message, state: FSMContext):
    path = await save_document(msg.document)
    await state.update_data(photo_path=str(path))

    await msg.answer("Photo received.\nNow send a video as a document.")
    await state.set_state(UploadMediaState.waiting_video)


@router.message(UploadMediaState.waiting_photo)
async def wrong_photo(msg: Message):
    await msg.answer("Please send a photo as document. No images/stickers/etc.")


@router.message(UploadMediaState.waiting_video, F.document)
async def receive_video(msg: Message, state: FSMContext):
    path = await save_document(msg.document)
    await state.update_data(video_path=str(path))

    await msg.answer("Video received.\nSend /generate to produce the result.")
    await state.set_state(UploadMediaState.ready_to_generate)


@router.message(UploadMediaState.waiting_video)
async def wrong_video(msg: Message):
    await msg.answer("Please send a video as document.")


@router.message(UploadMediaState.ready_to_generate, Command("generate"))
async def generate(msg: Message, state: FSMContext):
    data = await state.get_data()

    photo = data.get("photo_path")
    video = data.get("video_path")

    tasks.process_face_swap_task.delay(photo, video)

    await msg.answer("Generation scheduled...")
    await state.clear()


@router.message(UploadMediaState.ready_to_generate)
async def waiting_generate(msg: Message):
    await msg.answer("Send /generate to start.")


@router.message()
async def command_start_handler(msg: Message) -> None:
    await msg.answer("Press /start")


async def save_document(doc: Document) -> Path:
    file = await bot.get_file(doc.file_id)
    path = cache_folder / doc.file_name
    await bot.download_file(file.file_path, destination=path)
    return path
