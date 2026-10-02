import sqlite3
from dataclasses import replace, dataclass
from enum import StrEnum


class ManagedBotStatus(StrEnum):
    PENDING_CREATION = "pending_creation"
    AWAITING_ACTIVATION = "awaiting_activation"
    ACTIVE = "active"
    ERROR = "error"


@dataclass
class ManagedBotRow:
    id: int
    telegram_bot_id: int | None
    username: str
    name: str
    recipient_id: int
    recipient_username: str | None
    recipient_name: str | None
    remaining_seconds: int
    status: ManagedBotStatus


class ManagedBotsCrud:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    @staticmethod
    def _to_managed_bot(row: sqlite3.Row) -> ManagedBotRow:
        return ManagedBotRow(
            id=row["id"],
            telegram_bot_id=row["telegram_bot_id"],
            username=row["username"],
            name=row["name"],
            recipient_id=row["recipient_id"],
            recipient_username=row["recipient_username"],
            recipient_name=row["recipient_name"],
            remaining_seconds=row["remaining_seconds"],
            status=ManagedBotStatus(row["status"]),
        )

    def _get_by_id(self, bot_id: int) -> ManagedBotRow | None:
        row = self.connection.execute(
            "SELECT * FROM managed_bots WHERE id = ?", (bot_id,)
        ).fetchone()
        return self._to_managed_bot(row) if row else None

    def create(self, bot: ManagedBotRow) -> ManagedBotRow:
        cursor = self.connection.execute(
            """
            INSERT INTO managed_bots (
                telegram_bot_id,
                username,
                name,
                recipient_id,
                recipient_username,
                recipient_name,
                remaining_seconds,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bot.telegram_bot_id,
                bot.username,
                bot.name,
                bot.recipient_id,
                bot.recipient_username,
                bot.recipient_name,
                bot.remaining_seconds,
                bot.status,
            ),
        )
        return replace(bot, id=cursor.lastrowid)

    def get_by_id(self, bot_id: int) -> ManagedBotRow | None:
        return self._get_by_id(bot_id)

    def get_by_recipient_id(self, recipient_id: int) -> ManagedBotRow | None:
        row = self.connection.execute(
            "SELECT * FROM managed_bots WHERE recipient_id = ?", (recipient_id,)
        ).fetchone()
        return self._to_managed_bot(row) if row else None

    def get_by_username(self, username: str) -> ManagedBotRow | None:
        row = self.connection.execute(
            "SELECT * FROM managed_bots WHERE username = ?", (username,)
        ).fetchone()
        return self._to_managed_bot(row) if row else None

    def list_all(self) -> list[ManagedBotRow]:
        rows = self.connection.execute(
            "SELECT * FROM managed_bots ORDER BY id"
        ).fetchall()
        return [self._to_managed_bot(row) for row in rows]

    def update(self, bot: ManagedBotRow) -> ManagedBotRow:
        cursor = self.connection.execute(
            """
            UPDATE managed_bots
            SET
                telegram_bot_id = ?,
                username = ?,
                name = ?,
                recipient_id = ?,
                recipient_username = ?,
                recipient_name = ?,
                remaining_seconds = ?,
                status = ?
            WHERE id = ?
            """,
            (
                bot.telegram_bot_id,
                bot.username,
                bot.name,
                bot.recipient_id,
                bot.recipient_username,
                bot.recipient_name,
                bot.remaining_seconds,
                bot.status,
                bot.id,
            ),
        )
        if cursor.rowcount != 1:
            raise LookupError(f"Managed bot {bot.id} was not found")
        return bot

    def add_seconds(self, bot_id: int, seconds: int) -> ManagedBotRow | None:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        self.connection.execute(
            """
            UPDATE managed_bots
            SET remaining_seconds = remaining_seconds + ?
            WHERE id = ?
            """,
            (seconds, bot_id),
        )
        return self._get_by_id(bot_id)



