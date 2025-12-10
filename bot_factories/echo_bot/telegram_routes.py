from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

echo_router = Router()


@echo_router.message(Command("start"))
async def cmd_start(msg: Message):
    # Sends a basic greeting when the user starts the bot
    await msg.answer(
        "Hello! I’m your Telegram bot. Use /help to see available commands."
    )


@echo_router.message(Command("help"))
async def cmd_help(msg: Message):
    # Shows a list of available commands
    await msg.answer(
        "Here are the available commands:\n"
        "/start - Start interacting with the bot\n"
        "/help - Show this help message\n"
        "/about - Info about this bot\n"
        "/echo <text> - I will repeat your text"
    )


@echo_router.message(Command("about"))
async def cmd_about(msg: Message):
    # Basic info about the bot
    await msg.answer("I’m a simple bot created for demonstration purposes.")


@echo_router.message(Command("echo"))
async def cmd_echo(msg: Message):
    # Echoes back everything after the command
    parts = msg.text.split(maxsplit=1)
    if len(parts) == 1:
        await msg.answer("Please provide text to echo. Example: /echo hello")
    else:
        await msg.answer(parts[1])
