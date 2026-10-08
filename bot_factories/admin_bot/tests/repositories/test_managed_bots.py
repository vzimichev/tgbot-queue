from dataclasses import replace

import pytest

from bot_factories.admin_bot.db import db_engine
from bot_factories.admin_bot.db.managed_bot_limit_transactions import (
    VideoLimitConsumption,
)
from bot_factories.admin_bot.db.managed_bots import ManagedBotStatus
from bot_factories.admin_bot.repositories.managed_bots import ManagedBotsRepository


@pytest.fixture
def repository(tmp_path, monkeypatch):
    monkeypatch.setattr(db_engine, "database_path", tmp_path / "admin.sqlite3")
    return ManagedBotsRepository()


def test_create_register_and_reopen_pending_bot(repository):
    pending = repository.create_pending_bot(42, "alice", "Alice", 600)

    assert pending.status == ManagedBotStatus.PENDING_CREATION
    assert repository.get_by_recipient(42) == pending
    registered = repository.register_created_bot(99, pending.username, "Alice bot")

    assert registered.telegram_bot_id == 99
    assert registered.status == ManagedBotStatus.AWAITING_ACTIVATION
    assert repository.register_created_bot(99, pending.username, "Alice bot") == registered
    assert repository.get_by_telegram_bot_id(99) == registered


def test_repository_validates_unique_recipients_and_limits(repository):
    pending = repository.create_pending_bot(42, None, "Alice", 1)

    with pytest.raises(ValueError, match="already assigned"):
        repository.create_pending_bot(42, None, "Alice", 1)
    with pytest.raises(ValueError, match="positive"):
        repository.create_pending_bot(0, None, "Alice", 1)
    with pytest.raises(ValueError, match="positive"):
        repository.add_limit(pending.id, 0)
    with pytest.raises(LookupError):
        repository.add_limit(999, 1)


def test_register_rejects_changed_username_and_adds_limit(repository):
    pending = repository.create_pending_bot(42, None, "Alice", 5)

    assert repository.register_created_bot(99, "different_bot", "Bot") is None
    registered = repository.register_created_bot(99, pending.username, "Bot")
    assert repository.add_limit(registered.id, 10).remaining_seconds == 15
    assert repository.get_invitation(registered.id) == f"https://t.me/{pending.username}"


def test_consuming_video_limit_is_idempotent_and_never_overspends(repository):
    pending = repository.create_pending_bot(42, None, "Alice", 10)
    registered = repository.register_created_bot(99, pending.username, "Bot")
    assert registered is not None
    active = repository.save(replace(registered, status=ManagedBotStatus.ACTIVE))

    result, charged = repository.consume_video_limit(active.id, 101, 6)
    assert result == VideoLimitConsumption.CONSUMED
    assert charged is not None
    assert charged.remaining_seconds == 4

    duplicate, unchanged = repository.consume_video_limit(active.id, 101, 6)
    assert duplicate == VideoLimitConsumption.DUPLICATE
    assert unchanged is not None
    assert unchanged.remaining_seconds == 4

    insufficient, unchanged = repository.consume_video_limit(active.id, 102, 6)
    assert insufficient == VideoLimitConsumption.INSUFFICIENT
    assert unchanged is not None
    assert unchanged.remaining_seconds == 4
