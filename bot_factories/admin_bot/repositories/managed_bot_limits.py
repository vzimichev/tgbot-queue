import sqlite3
from dataclasses import replace

from bot_factories.admin_bot.db.db_engine import transactional
from bot_factories.admin_bot.db.managed_bot_limit_transactions import (
    LimitTransactionType,
    ManagedBotLimitTransactionsCrud,
    VideoLimitConsumption,
)
from bot_factories.admin_bot.db.managed_bots import (
    ManagedBotRow,
    ManagedBotStatus,
    ManagedBotsCrud,
)


class ManagedBotLimitsRepository:
    """Limit ledger independent from a managed bot's implementation type."""

    @staticmethod
    def with_balance(
        bot: ManagedBotRow | None, connection: sqlite3.Connection
    ) -> ManagedBotRow | None:
        if bot is None:
            return None
        balance = ManagedBotLimitTransactionsCrud(connection).balance(bot.id)
        return replace(bot, remaining_seconds=balance)

    @staticmethod
    def create_opening_balance(
        managed_bot_id: int, seconds: int, connection: sqlite3.Connection
    ) -> None:
        ManagedBotLimitTransactionsCrud(connection).add(
            managed_bot_id, seconds, LimitTransactionType.OPENING_BALANCE
        )

    @transactional
    def add_limit(
        self, bot_id: int, seconds: int, *, connection: sqlite3.Connection
    ) -> ManagedBotRow:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        bot = ManagedBotsCrud(connection).get_by_id(bot_id)
        if bot is None:
            raise LookupError(f"Managed bot {bot_id} was not found")
        ManagedBotLimitTransactionsCrud(connection).add(
            bot_id, seconds, LimitTransactionType.TOP_UP
        )
        enriched = self.with_balance(bot, connection)
        assert enriched is not None
        return enriched

    @transactional
    def consume_video_limit(
        self,
        bot_id: int,
        update_id: int,
        seconds: int,
        *,
        connection: sqlite3.Connection,
    ) -> tuple[VideoLimitConsumption, ManagedBotRow | None]:
        if update_id < 0:
            raise ValueError("update_id must not be negative")
        if seconds < 0:
            raise ValueError("seconds must not be negative")

        connection.execute("BEGIN IMMEDIATE")
        bot = ManagedBotsCrud(connection).get_by_id(bot_id)
        if bot is None or bot.status != ManagedBotStatus.ACTIVE:
            return VideoLimitConsumption.INACTIVE, bot
        transactions = ManagedBotLimitTransactionsCrud(connection)
        if transactions.has_video_debit(bot_id, update_id):
            return VideoLimitConsumption.DUPLICATE, self.with_balance(bot, connection)
        if transactions.balance(bot_id) < seconds:
            return VideoLimitConsumption.INSUFFICIENT, self.with_balance(bot, connection)
        transactions.add(
            bot_id,
            -seconds,
            LimitTransactionType.VIDEO_DEBIT,
            webhook_update_id=update_id,
        )
        return VideoLimitConsumption.CONSUMED, self.with_balance(bot, connection)
