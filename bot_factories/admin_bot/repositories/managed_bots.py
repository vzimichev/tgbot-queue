import secrets
import sqlite3
from dataclasses import replace

from bot_factories.admin_bot.db.db_engine import transaction, transactional
from bot_factories.admin_bot.db.managed_bots import (
    ManagedBotRow,
    ManagedBotStatus,
    ManagedBotsCrud,
)

SUGGESTED_BOT_NAME = "My faceswap bot"


class ManagedBotsRepository:
    @transactional
    def get_by_recipient(
        self,
        recipient_id: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow | None:
        return ManagedBotsCrud(connection).get_by_recipient_id(recipient_id)

    @transactional
    def get_by_telegram_bot_id(
        self,
        telegram_bot_id: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow | None:
        return ManagedBotsCrud(connection).get_by_telegram_bot_id(telegram_bot_id)

    @transactional
    def get_bot(
        self,
        bot_id: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow | None:
        return ManagedBotsCrud(connection).get_by_id(bot_id)

    @transactional
    def list_bots(
        self,
        *,
        connection: sqlite3.Connection,
    ) -> list[ManagedBotRow]:
        return ManagedBotsCrud(connection).list_all()

    @transactional
    def create_pending_bot(
        self,
        recipient_id: int,
        recipient_username: str | None,
        recipient_name: str | None,
        initial_seconds: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow:
        if recipient_id <= 0:
            raise ValueError("recipient_id must be positive")
        if initial_seconds <= 0:
            raise ValueError("initial_seconds must be positive")

        crud = ManagedBotsCrud(connection)
        if crud.get_by_recipient_id(recipient_id):
            raise ValueError("A bot is already assigned to this recipient")

        for _ in range(10):
            username = f"personal_{secrets.token_hex(6)}_bot"
            if crud.get_by_username(username) is None:
                return crud.create(
                    ManagedBotRow(
                        id=0,
                        telegram_bot_id=None,
                        username=username,
                        name=SUGGESTED_BOT_NAME,
                        recipient_id=recipient_id,
                        recipient_username=recipient_username,
                        recipient_name=recipient_name,
                        remaining_seconds=initial_seconds,
                        status=ManagedBotStatus.PENDING_CREATION,
                    )
                )

        raise RuntimeError("Could not generate a unique bot username")

    def register_created_bot(
        self,
        telegram_bot_id: int,
        username: str,
        name: str,
    ) -> ManagedBotRow | None:
        if telegram_bot_id <= 0:
            raise ValueError("telegram_bot_id must be positive")
        if not username:
            raise ValueError("username is required")
        if not name:
            raise ValueError("name is required")

        with transaction() as connection:
            bot = ManagedBotsCrud(connection).get_by_username(username)

        if bot is None:
            return None
        if bot.telegram_bot_id is not None:
            if bot.telegram_bot_id == telegram_bot_id:
                return bot
            raise ValueError("The suggested username is already registered")

        registered_bot = replace(
            bot,
            telegram_bot_id=telegram_bot_id,
            username=username,
            name=name,
            status=ManagedBotStatus.AWAITING_ACTIVATION,
        )
        with transaction() as connection:
            return ManagedBotsCrud(connection).update(registered_bot)

    @transactional
    def save(
        self,
        bot: ManagedBotRow,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow:
        return ManagedBotsCrud(connection).update(bot)

    @transactional
    def add_limit(
        self,
        bot_id: int,
        seconds: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        bot = ManagedBotsCrud(connection).add_seconds(bot_id, seconds)
        if bot is None:
            raise LookupError(f"Managed bot {bot_id} was not found")
        return bot

    def get_invitation(self, bot_id: int) -> str:
        bot = self.get_bot(bot_id)
        if bot is None:
            raise LookupError(f"Managed bot {bot_id} was not found")
        return f"https://t.me/{bot.username}"
