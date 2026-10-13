import secrets
import sqlite3
from dataclasses import dataclass, replace
from enum import StrEnum

from bot_factories.admin_bot.db.db_engine import transaction, transactional
from bot_factories.admin_bot.db.managed_bot_transactions import (
    ManagedBotTransactionsCrud,
)
from bot_factories.admin_bot.db.managed_bots import (
    ManagedBotRow,
    ManagedBotStatus,
    ManagedBotsCrud,
)

SUGGESTED_BOT_NAME = "My faceswap bot"


class ManagedBotAccountResult(StrEnum):
    AVAILABLE = "available"
    INACTIVE = "inactive"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class ManagedBotAccount:
    """The recipient-visible ledger state for one managed bot."""

    result: ManagedBotAccountResult
    remaining_seconds: int | None = None
    transactions: tuple = ()


class ManagedBotsRepository:
    @transactional
    def get_by_recipient(
        self,
        recipient_id: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow | None:
        return self._with_balance(
            ManagedBotsCrud(connection).get_by_recipient_id(recipient_id), connection
        )

    @transactional
    def get_by_telegram_bot_id(
        self,
        telegram_bot_id: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow | None:
        return self._with_balance(
            ManagedBotsCrud(connection).get_by_telegram_bot_id(telegram_bot_id),
            connection,
        )

    @transactional
    def get_bot(
        self,
        bot_id: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow | None:
        return self._with_balance(
            ManagedBotsCrud(connection).get_by_id(bot_id), connection
        )

    @transactional
    def get_managed_bot_account(
        self,
        telegram_bot_id: int,
        telegram_user_id: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotAccount:
        """Return balance and recent ledger entries only to the assigned recipient."""
        bot = ManagedBotsCrud(connection).get_by_telegram_bot_id(telegram_bot_id)
        if bot is None or bot.status != ManagedBotStatus.ACTIVE:
            return ManagedBotAccount(ManagedBotAccountResult.INACTIVE)
        if bot.recipient_id != telegram_user_id:
            return ManagedBotAccount(ManagedBotAccountResult.FORBIDDEN)

        transactions = ManagedBotTransactionsCrud(connection)
        return ManagedBotAccount(
            ManagedBotAccountResult.AVAILABLE,
            remaining_seconds=transactions.balance(bot.id),
            transactions=tuple(transactions.list_for_managed_bot(bot.id, limit=20)),
        )

    @transactional
    def list_bots(
        self,
        *,
        connection: sqlite3.Connection,
    ) -> list[ManagedBotRow]:
        return [
            self._with_balance(bot, connection)
            for bot in ManagedBotsCrud(connection).list_all()
        ]

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
                bot = crud.create(
                    ManagedBotRow(
                        id=0,
                        telegram_bot_id=None,
                        username=username,
                        name=SUGGESTED_BOT_NAME,
                        recipient_id=recipient_id,
                        recipient_username=recipient_username,
                        recipient_name=recipient_name,
                        remaining_seconds=0,
                        status=ManagedBotStatus.PENDING_CREATION,
                    )
                )
                ManagedBotTransactionsCrud(connection).add(
                    bot.id, initial_seconds, "opening_balance"
                )
                return self._with_balance(bot, connection)

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
                return self.get_bot(bot.id)
            raise ValueError("The suggested username is already registered")

        registered_bot = replace(
            bot,
            telegram_bot_id=telegram_bot_id,
            username=username,
            name=name,
            status=ManagedBotStatus.AWAITING_ACTIVATION,
        )
        with transaction() as connection:
            saved = ManagedBotsCrud(connection).update(registered_bot)
            return self._with_balance(saved, connection)

    @transactional
    def save(
        self,
        bot: ManagedBotRow,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotRow:
        crud = ManagedBotsCrud(connection)
        persisted = crud.get_by_id(bot.id)
        if persisted is None:
            raise LookupError(f"Managed bot {bot.id} was not found")
        # The legacy column is no longer a balance cache.  Preserve it while
        # saving lifecycle fields, because the transaction ledger is canonical.
        saved = crud.update(replace(bot, remaining_seconds=persisted.remaining_seconds))
        return self._with_balance(saved, connection)

    def get_invitation(self, bot_id: int) -> str:
        bot = self.get_bot(bot_id)
        if bot is None:
            raise LookupError(f"Managed bot {bot_id} was not found")
        return f"https://t.me/{bot.username}"

    @staticmethod
    def _with_balance(
        bot: ManagedBotRow | None, connection: sqlite3.Connection
    ) -> ManagedBotRow | None:
        if bot is None:
            return None
        return replace(
            bot,
            remaining_seconds=ManagedBotTransactionsCrud(connection).balance(bot.id),
        )
