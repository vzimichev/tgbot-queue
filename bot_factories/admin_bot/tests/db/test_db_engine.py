from pathlib import Path

import pytest

from bot_factories.admin_bot.db import db_engine


def test_transaction_commits_and_rolls_back(monkeypatch, tmp_path):
    monkeypatch.setattr(db_engine, "database_path", Path(tmp_path / "admin.sqlite3"))

    with db_engine.transaction() as connection:
        connection.execute("INSERT INTO managed_bots (username, name, recipient_id, remaining_seconds, status) VALUES ('one_bot', 'One', 1, 0, 'pending_creation')")

    with pytest.raises(RuntimeError):
        with db_engine.transaction() as connection:
            connection.execute("INSERT INTO managed_bots (username, name, recipient_id, remaining_seconds, status) VALUES ('two_bot', 'Two', 2, 0, 'pending_creation')")
            raise RuntimeError("rollback")

    with db_engine.transaction() as connection:
        assert connection.execute("SELECT COUNT(*) FROM managed_bots").fetchone()[0] == 1


def test_transactional_injects_connection_and_rejects_manual_one(monkeypatch, tmp_path):
    monkeypatch.setattr(db_engine, "database_path", tmp_path / "admin.sqlite3")

    @db_engine.transactional
    def operation(value, *, connection):
        return value, connection.execute("SELECT 1").fetchone()[0]

    assert operation("ok") == ("ok", 1)
    with pytest.raises(TypeError, match="managed"):
        operation("no", connection=None)
