import sqlite3
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

    def add(
        self,
        managed_bot_id: int,
        seconds: int,
        transaction_type: LimitTransactionType,
        *,
        webhook_update_id: int | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO managed_bot_limit_transactions (
                managed_bot_id, seconds, transaction_type, webhook_update_id
            ) VALUES (?, ?, ?, ?)
            """,
            (managed_bot_id, seconds, transaction_type, webhook_update_id),
        )
