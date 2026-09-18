"""Webhook for the lightweight managed-bot administrator."""

import os
import threading
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from bot_factories.admin_bot.config import admin_settings
from bot_factories.admin_bot.repository import Repository
from bot_factories.admin_bot.service import AdminService
from bot_factories.admin_bot.telegram import TelegramAPI

_update_lock = threading.Lock()


def process_admin_update(body: dict[str, Any]):
    if not admin_settings.token.get_secret_value() or admin_settings.owner_id <= 0:
        raise HTTPException(status_code=503, detail="Admin webhook is not configured")
    update_id = body.get("update_id")
    if type(update_id) is not int or update_id < 0:
        raise HTTPException(status_code=400, detail="Invalid update")

    folder = Path(
        os.environ.get(
            "ADMIN_BOT_DATA_DIR",
            Path(__file__).parents[1] / "bot_factories/admin_bot/.cache",
        )
    )
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    with _update_lock:
        repo = Repository(folder / "admin.sqlite3")
        try:
            if update_id >= (repo.get("offset") or 0):
                service = AdminService(
                    TelegramAPI(admin_settings.token.get_secret_value()),
                    repo,
                    admin_settings.owner_id,
                )
                service.handle(body)
                repo.put("offset", update_id + 1)
        finally:
            repo.db.close()
    return {"ok": True}
