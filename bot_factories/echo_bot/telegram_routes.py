from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

echo_router = Router()


@echo_router.message(Command("start"))
async def start(msg: Message):
    await msg.answer("Hello World")
