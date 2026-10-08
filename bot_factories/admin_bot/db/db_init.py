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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS managed_bot_limit_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            managed_bot_id INTEGER NOT NULL REFERENCES managed_bots(id),
            seconds INTEGER NOT NULL,
            transaction_type TEXT NOT NULL CHECK (
                transaction_type IN ('opening_balance', 'top_up', 'video_debit')
            ),
            webhook_update_id INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS managed_bot_limit_transactions_video_update_idx
        ON managed_bot_limit_transactions(managed_bot_id, webhook_update_id)
        WHERE webhook_update_id IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS managed_bot_limit_transactions_opening_idx
        ON managed_bot_limit_transactions(managed_bot_id)
        WHERE transaction_type = 'opening_balance'
        """
    )
    connection.execute(
        """
        INSERT INTO managed_bot_limit_transactions (
            managed_bot_id, seconds, transaction_type
        )
        SELECT id, remaining_seconds, 'opening_balance'
        FROM managed_bots
        WHERE NOT EXISTS (
            SELECT 1 FROM managed_bot_limit_transactions
            WHERE managed_bot_id = managed_bots.id
              AND transaction_type = 'opening_balance'
        )
        """
    )
    connection.commit()
