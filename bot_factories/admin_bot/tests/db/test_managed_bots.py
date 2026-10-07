import sqlite3

import pytest

from bot_factories.admin_bot.db.db_init import initialize
from bot_factories.admin_bot.db.managed_bots import (
    ManagedBotStatus,
    ManagedBotsCrud,
)


@pytest.fixture
def crud():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize(connection)
    yield ManagedBotsCrud(connection)
    connection.close()


def test_crud_round_trip_and_lookup_methods(crud, managed_bot):
    saved = crud.create(managed_bot())

    assert saved.id == 1
    assert crud.get_by_id(saved.id) == saved
    assert crud.get_by_recipient_id(7) == saved
    assert crud.get_by_telegram_bot_id(99) == saved
    assert crud.get_by_username("personal_bot") == saved
    assert crud.list_all() == [saved]


def test_update_and_add_seconds_keep_persisted_values(crud, managed_bot):
    saved = crud.create(managed_bot(telegram_bot_id=None))
    updated = managed_bot(
        id=saved.id,
        telegram_bot_id=99,
        status=ManagedBotStatus.ACTIVE,
        remaining_seconds=61,
    )

    assert crud.update(updated) == updated
    assert crud.add_seconds(saved.id, 39).remaining_seconds == 100
    with pytest.raises(ValueError, match="positive"):
        crud.add_seconds(saved.id, 0)
    with pytest.raises(LookupError):
        crud.update(managed_bot(id=999))


def test_initialize_upgrades_legacy_table_with_activation_columns():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE managed_bots (
            id INTEGER PRIMARY KEY, telegram_bot_id INTEGER UNIQUE,
            username TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            recipient_id INTEGER NOT NULL UNIQUE, recipient_username TEXT,
            recipient_name TEXT, remaining_seconds INTEGER NOT NULL,
            status TEXT NOT NULL
        )
        """
    )

    initialize(connection)

    columns = {row[1] for row in connection.execute("PRAGMA table_info(managed_bots)")}
    assert {"child_bot_token", "claim_token", "access_mode", "activation_error"} <= columns
