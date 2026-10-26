import asyncio
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import FSInputFile, Update
from celery import shared_task

from bot_factories.admin_bot.faceswap import process_faceswap_task, save_media
from bot_factories.admin_bot.job_names import (
    MANAGED_BOT_UPDATES_TASK,
    MANAGED_FACESWAP_TASK,
)
from bot_factories.admin_bot.repositories.bot_manager import ManagedBotsRepository
from bot_factories.admin_bot.routes.managed_bot import managed_bot_router


managed_bot_dispatcher = Dispatcher()
managed_bot_dispatcher.include_router(managed_bot_router)


def managed_bot_token(bot_id: int) -> str | None:
    bot = ManagedBotsRepository().get_by_telegram_bot_id(bot_id)
    return bot.child_bot_token if bot else None


@shared_task(name=MANAGED_BOT_UPDATES_TASK)
def managed_bot_updates(bot_id: int, body: dict[str, Any]) -> dict[str, str]:
    token = managed_bot_token(bot_id)
    update_id = body.get("update_id")
    if not token or not isinstance(update_id, int):
        return {"status": "ignored"}

    async def dispatch() -> dict[str, str]:
        bot = Bot(token=token)
        try:
            return await managed_bot_dispatcher.feed_update(
                bot=bot,
                update=Update.model_validate(body),
                managed_bot_id=bot_id,
                managed_update_id=update_id,
            )
        finally:
            await bot.session.close()

    return asyncio.run(dispatch())


@shared_task(name=MANAGED_FACESWAP_TASK)
def process_managed_faceswap(
    bot_token: str, chat_id: int, media: dict[str, str]
) -> dict[str, str]:
    """Run one managed FaceSwap request on the local GPU worker."""
    if not bot_token:
        return {"status": "ignored"}

    async def run() -> dict[str, str]:
        bot = Bot(token=bot_token)
        progress_message = await bot.send_message(
            chat_id, "Face swap: 0% — preparing inputs"
        )
        last_progress = ("", -1)

        async def report_progress(status: dict) -> None:
            nonlocal last_progress
            stage = str(status.get("stage", "processing"))
            percent = int(status.get("percent", 0))
            current = (stage, percent)
            if current == last_progress:
                return
            last_progress = current
            try:
                await progress_message.edit_text(
                    f"Face swap: {percent}% — {stage.replace('_', ' ')}"
                )
            except Exception:
                # A deleted status message must not discard an otherwise valid job.
                pass

        try:
            photo_path = await save_media(
                bot, media["photo_file_id"], media["photo_file_name"]
            )
            video_path = await save_media(
                bot, media["video_file_id"], media["video_file_name"]
            )
            output_path = await process_faceswap_task(
                photo_path, video_path, report_progress
            )
            await progress_message.edit_text("Face swap: 100% — uploading result")
            await bot.send_document(
                chat_id, FSInputFile(output_path), caption="Face swap complete."
            )
            await progress_message.edit_text("Face swap complete — 100%")
            return {"status": "complete"}
        except Exception:
            await progress_message.edit_text("Face swap failed. Check the worker log.")
            raise
        finally:
            await bot.session.close()

    return asyncio.run(run())
