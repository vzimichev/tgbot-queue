import sqlite3

from bot_factories.admin_bot.db.db_init import initialize
from bot_factories.admin_bot.db.managed_bot_limit_transactions import (
    LimitTransactionType,
    ManagedBotLimitTransactionsCrud,
)


def test_transaction_crud_records_and_calculates_a_balance():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize(connection)
    connection.execute(
        """
        INSERT INTO managed_bots (username, name, recipient_id, remaining_seconds, status)
        VALUES ('personal_bot', 'Personal', 7, 0, 'active')
        """
    )
    transactions = ManagedBotLimitTransactionsCrud(connection)

    opening = transactions.add(1, 60, LimitTransactionType.OPENING_BALANCE)
    debit = transactions.add(
        1, -12, LimitTransactionType.VIDEO_DEBIT, webhook_update_id=101
    )

    assert transactions.balance(1) == 48
    assert transactions.has_video_debit(1, 101)
    assert opening.seconds == 60
    assert debit.webhook_update_id == 101
    assert transactions.get_by_id(debit.id) == debit
    assert transactions.list_for_managed_bot(1) == [opening, debit]
