import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class LimitTransactionType(StrEnum):
    OPENING_BALANCE = "opening_balance"
    TOP_UP = "top_up"
    VIDEO_DEBIT = "video_debit"


class VideoLimitConsumption(StrEnum):
    CONSUMED = "consumed"
    DUPLICATE = "duplicate"
    INSUFFICIENT = "insufficient"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class ManagedBotLimitTransactionRow:
    id: int
    managed_bot_id: int
    seconds: int
    transaction_type: LimitTransactionType
    webhook_update_id: int | None
    created_at: datetime


class ManagedBotLimitTransactionsCrud:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def balance(self, managed_bot_id: int) -> int:
        row = self.connection.execute(
            """
            SELECT COALESCE(SUM(seconds), 0) AS balance
            FROM managed_bot_limit_transactions
            WHERE managed_bot_id = ?
            """,
            (managed_bot_id,),
        ).fetchone()
        return int(row["balance"])

    def has_video_debit(self, managed_bot_id: int, webhook_update_id: int) -> bool:
        return (
            self.connection.execute(
                """
                SELECT 1 FROM managed_bot_limit_transactions
                WHERE managed_bot_id = ? AND webhook_update_id = ?
                """,
                (managed_bot_id, webhook_update_id),
            ).fetchone()
            is not None
        )

    @staticmethod
    def _to_transaction(row: sqlite3.Row) -> ManagedBotLimitTransactionRow:
        return ManagedBotLimitTransactionRow(
            id=row["id"],
            managed_bot_id=row["managed_bot_id"],
            seconds=row["seconds"],
            transaction_type=LimitTransactionType(row["transaction_type"]),
            webhook_update_id=row["webhook_update_id"],
            created_at=datetime.fromisoformat(row["created_at"].replace(" ", "T")),
        )

    def get_by_id(self, transaction_id: int) -> ManagedBotLimitTransactionRow | None:
        row = self.connection.execute(
            "SELECT * FROM managed_bot_limit_transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        return self._to_transaction(row) if row else None

    def list_for_managed_bot(
        self, managed_bot_id: int
    ) -> list[ManagedBotLimitTransactionRow]:
        rows = self.connection.execute(
            """
            SELECT * FROM managed_bot_limit_transactions
            WHERE managed_bot_id = ?
            ORDER BY id
            """,
            (managed_bot_id,),
        ).fetchall()
        return [self._to_transaction(row) for row in rows]

    def add(
        self,
        managed_bot_id: int,
        seconds: int,
        transaction_type: LimitTransactionType,
        *,
        webhook_update_id: int | None = None,
    ) -> ManagedBotLimitTransactionRow:
        cursor = self.connection.execute(
            """
            INSERT INTO managed_bot_limit_transactions (
                managed_bot_id, seconds, transaction_type, webhook_update_id
            ) VALUES (?, ?, ?, ?)
            """,
            (managed_bot_id, seconds, transaction_type, webhook_update_id),
        )
        transaction = self.get_by_id(cursor.lastrowid)
        assert transaction is not None
        return transaction
