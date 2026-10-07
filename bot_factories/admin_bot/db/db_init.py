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
            ),
            child_bot_token TEXT,
            claim_token TEXT UNIQUE,
            claim_webhook_update_id INTEGER,
            access_mode TEXT CHECK (access_mode IN ('telegram', 'application')),
            activation_error TEXT
        )
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(managed_bots)")}
    migrations = {
        "child_bot_token": "ALTER TABLE managed_bots ADD COLUMN child_bot_token TEXT",
        "claim_token": "ALTER TABLE managed_bots ADD COLUMN claim_token TEXT",
        "claim_webhook_update_id": "ALTER TABLE managed_bots ADD COLUMN claim_webhook_update_id INTEGER",
        "access_mode": "ALTER TABLE managed_bots ADD COLUMN access_mode TEXT",
        "activation_error": "ALTER TABLE managed_bots ADD COLUMN activation_error TEXT",
    }
    for name, statement in migrations.items():
        if name not in columns:
            connection.execute(statement)
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS managed_bots_claim_token_idx "
        "ON managed_bots(claim_token) WHERE claim_token IS NOT NULL"
    )
    connection.commit()
