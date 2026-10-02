import sqlite3


def initialize(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS managed_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_bot_id INTEGER UNIQUE,
            username TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            recipient_id INTEGER NOT NULL UNIQUE,
            recipient_username TEXT,
            recipient_name TEXT,
            remaining_seconds INTEGER NOT NULL CHECK (remaining_seconds >= 0),
            status TEXT NOT NULL CHECK (
                status IN (
                    'pending_creation',
                    'awaiting_activation',
                    'active',
                    'error'
                )
            )
        )
        """
    )
    connection.commit()
