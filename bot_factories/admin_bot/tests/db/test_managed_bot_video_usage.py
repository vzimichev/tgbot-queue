import sqlite3

from bot_factories.admin_bot.db.db_init import initialize
from bot_factories.admin_bot.db.managed_bot_video_usage import ManagedBotVideoUsageCrud


def test_usage_crud_creates_and_finds_one_webhook_charge():
    connection = sqlite3.connect(":memory:")
    initialize(connection)
    connection.execute(
        """
        INSERT INTO managed_bots (username, name, recipient_id, remaining_seconds, status)
        VALUES ('personal_bot', 'Personal', 7, 60, 'active')
        """
    )
    usage = ManagedBotVideoUsageCrud(connection)

    assert not usage.exists(1, 101)
    usage.create(1, 101, 12)
    assert usage.exists(1, 101)
