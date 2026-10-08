import sqlite3
from enum import StrEnum


class VideoLimitConsumption(StrEnum):
    CONSUMED = "consumed"
    DUPLICATE = "duplicate"
    INSUFFICIENT = "insufficient"
    INACTIVE = "inactive"


class ManagedBotVideoUsageCrud:
    """Persistence operations for one charged video per Telegram update."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def exists(self, managed_bot_id: int, webhook_update_id: int) -> bool:
        return (
            self.connection.execute(
                """
                SELECT 1 FROM managed_bot_video_usage
                WHERE managed_bot_id = ? AND webhook_update_id = ?
                """,
                (managed_bot_id, webhook_update_id),
            ).fetchone()
            is not None
        )

    def create(
        self,
        managed_bot_id: int,
        webhook_update_id: int,
        seconds: int,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO managed_bot_video_usage (
                managed_bot_id, webhook_update_id, seconds
            ) VALUES (?, ?, ?)
            """,
            (managed_bot_id, webhook_update_id, seconds),
        )
