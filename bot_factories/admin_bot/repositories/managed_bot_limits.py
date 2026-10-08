import sqlite3

from bot_factories.admin_bot.db.db_engine import transactional
from bot_factories.admin_bot.db.managed_bot_limit_transactions import (
    LimitTransactionType,
    ManagedBotLimitTransactionsCrud,
    VideoLimitConsumption,
)


class ManagedBotLimitsRepository:
    """Limit ledger independent from a managed bot's implementation type."""

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
    ) -> int:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        try:
            ManagedBotLimitTransactionsCrud(connection).add(
                bot_id, seconds, LimitTransactionType.TOP_UP
            )
        except sqlite3.IntegrityError as error:
            raise LookupError(f"Managed bot {bot_id} was not found") from error
        return ManagedBotLimitTransactionsCrud(connection).balance(bot_id)

    @transactional
    def consume_video_limit(
        self,
        bot_id: int,
        update_id: int,
        seconds: int,
        *,
        connection: sqlite3.Connection,
    ) -> tuple[VideoLimitConsumption, int]:
        if update_id < 0:
            raise ValueError("update_id must not be negative")
        if seconds < 0:
            raise ValueError("seconds must not be negative")

        connection.execute("BEGIN IMMEDIATE")
        transactions = ManagedBotLimitTransactionsCrud(connection)
        if transactions.has_video_debit(bot_id, update_id):
            return VideoLimitConsumption.DUPLICATE, transactions.balance(bot_id)
        if transactions.balance(bot_id) < seconds:
            return VideoLimitConsumption.INSUFFICIENT, transactions.balance(bot_id)
        transactions.add(
            bot_id,
            -seconds,
            LimitTransactionType.VIDEO_DEBIT,
            webhook_update_id=update_id,
        )
        return VideoLimitConsumption.CONSUMED, transactions.balance(bot_id)
