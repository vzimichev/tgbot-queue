from pathlib import Path

from aiogram import Router
from aiogram.types import Message

from worker.telegram.bot import bot

common_router = Router()

cache_folder = Path(__file__).parent.parent / ".cache"


@common_router.message()
async def download_file(msg: Message):
    tmp_folder = f"{msg.date}-{msg.media_group_id}"
    dest_dir = cache_folder / tmp_folder

    file_paths = []
    if msg.document:
        dest_dir.mkdir(parents=True, exist_ok=True)
        file = await bot.get_file(msg.document.file_id)
        path = dest_dir / msg.document.file_name
        await bot.download_file(file.file_path, destination=path)
        file_paths.append(path)

    await msg.answer(f"{len(file_paths)} file(s) downloaded.")
