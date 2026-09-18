"""Standalone admin bot: python -m bot_factories.admin_bot.polling."""

import logging
import os
import time
from pathlib import Path

from bot_factories.admin_bot.config import admin_settings
from bot_factories.admin_bot.repository import Repository
from bot_factories.admin_bot.service import AdminService
from bot_factories.admin_bot.telegram import TelegramAPI


def main():
    os.umask(0o077)
    config = admin_settings
    if not config.token.get_secret_value() or config.owner_id <= 0:
        raise SystemExit("Admin bot token and owner ID are required")
    folder = Path(os.environ.get("ADMIN_BOT_DATA_DIR", Path(__file__).parent / ".cache"))
    folder.mkdir(parents=True, exist_ok=True)
    # Prevent two local polling processes from consuming the same bot's updates.
    import fcntl

    lock = (folder / "polling.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    repo = Repository(folder / "admin.sqlite3")
    api = TelegramAPI(config.token.get_secret_value())
    me = api.call("getMe")
    api.call("deleteWebhook", drop_pending_updates=False)
    service = AdminService(api, repo, config.owner_id)
    print(f"Admin bot running: https://t.me/{me['username']}", flush=True)
    while True:
        try:
            updates = api.call(
                "getUpdates",
                offset=repo.get("offset") or 0,
                timeout=20,
                allowed_updates=["message", "managed_bot"],
            )
            for update in updates:
                service.handle(update)
                repo.put("offset", update["update_id"] + 1)
        except RuntimeError as error:
            logging.warning("%s; retrying in 5 seconds", error)
            time.sleep(5)


if __name__ == "__main__":
    main()
