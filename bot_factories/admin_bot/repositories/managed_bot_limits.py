import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from bot_factories.admin_bot.db.db_engine import transactional
from bot_factories.admin_bot.db.managed_bot_limit_transactions import (
    LimitTransactionType,
    ManagedBotLimitTransactionsCrud,
    VideoLimitConsumption,
)
from bot_factories.admin_bot.db.managed_bots import ManagedBotStatus, ManagedBotsCrud


class ManagedBotVideoLimitResult(StrEnum):
    CONSUMED = "consumed"
    DUPLICATE = "duplicate"
    INSUFFICIENT = "insufficient"
    INACTIVE = "inactive"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class ManagedBotVideoLimitCharge:
    result: ManagedBotVideoLimitResult
    remaining_seconds: int | None = None


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

    @transactional
    def charge_video(
        self,
        telegram_bot_id: int,
        telegram_user_id: int,
        update_id: int,
        duration_seconds: int,
        *,
        connection: sqlite3.Connection,
    ) -> ManagedBotVideoLimitCharge:
        """Authorize and charge one incoming video for a managed bot."""
        if update_id < 0:
            raise ValueError("update_id must not be negative")
        if duration_seconds < 0:
            raise ValueError("duration_seconds must not be negative")

        connection.execute("BEGIN IMMEDIATE")
        bot = ManagedBotsCrud(connection).get_by_telegram_bot_id(telegram_bot_id)
        if bot is None or bot.status != ManagedBotStatus.ACTIVE:
            return ManagedBotVideoLimitCharge(ManagedBotVideoLimitResult.INACTIVE)
        if bot.recipient_id != telegram_user_id:
            return ManagedBotVideoLimitCharge(ManagedBotVideoLimitResult.FORBIDDEN)

        transactions = ManagedBotLimitTransactionsCrud(connection)
        if transactions.has_video_debit(bot.id, update_id):
            return ManagedBotVideoLimitCharge(
                ManagedBotVideoLimitResult.DUPLICATE, transactions.balance(bot.id)
            )
        if transactions.balance(bot.id) < duration_seconds:
            return ManagedBotVideoLimitCharge(
                ManagedBotVideoLimitResult.INSUFFICIENT, transactions.balance(bot.id)
            )
        transactions.add(
            bot.id,
            -duration_seconds,
            LimitTransactionType.VIDEO_DEBIT,
            webhook_update_id=update_id,
        )
        return ManagedBotVideoLimitCharge(
            ManagedBotVideoLimitResult.CONSUMED, transactions.balance(bot.id)
        )
