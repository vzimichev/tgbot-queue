import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bot_factories.admin_bot import telegram_routes as routes
from bot_factories.admin_bot.db.managed_bot_limit_transactions import (
    VideoLimitConsumption,
)
from bot_factories.admin_bot.db.managed_bots import ActivationResult, ManagedBotStatus


def test_parse_seconds_accepts_only_positive_ascii_integers():
    assert routes._parse_seconds(" 10 ") == 10
    for value in (None, "", "0", "-1", "1.5", "²"):
        assert routes._parse_seconds(value) is None


def test_is_owner_rejects_groups_and_other_users(monkeypatch):
    monkeypatch.setattr(routes.admin_bot_settings, "owner_id", 7)

    def event(user_id, chat_id):
        return SimpleNamespace(
            from_user=SimpleNamespace(id=user_id),
            message=SimpleNamespace(chat=SimpleNamespace(id=chat_id)),
        )

    assert routes.is_owner(event(7, 7))
    assert not routes.is_owner(event(8, 8))
    assert not routes.is_owner(event(7, -7))


def test_recover_card_activation_skips_active_and_complete_records(monkeypatch, managed_bot):
    recovered = Mock()
    monkeypatch.setattr(routes.activation_service, "recover_activation", recovered)

    active = managed_bot(status=ManagedBotStatus.ACTIVE)
    ready = managed_bot(child_bot_token="child", claim_token="claim")
    failed = managed_bot(status=ManagedBotStatus.ERROR)
    recovered.return_value = ready

    assert asyncio.run(routes.recover_card_activation(active)) == active
    assert asyncio.run(routes.recover_card_activation(ready)) == ready
    assert asyncio.run(routes.recover_card_activation(failed)) == ready
    recovered.assert_called_once_with(failed.id)


def test_managed_message_returns_status_and_only_sends_known_responses(monkeypatch):
    message = SimpleNamespace(
        text="/start claim_secret",
        from_user=SimpleNamespace(id=42, username="alice", first_name="Alice"),
        answer=AsyncMock(),
    )
    handler = Mock(return_value=ActivationResult.CONFIGURED)
    monkeypatch.setattr(routes.activation_service, "handle_claim", handler)

    result = asyncio.run(routes.process_managed_bot_message(message, 99, 12))

    assert result == {"status": "configured"}
    assert handler.call_args.kwargs["claimant_id"] == 42
    message.answer.assert_awaited_once()


def test_managed_message_without_sender_is_ignored():
    message = SimpleNamespace(from_user=None)

    assert asyncio.run(routes.process_managed_bot_message(message, 99, 12)) == {"status": "ignored"}


def test_active_managed_bot_charges_the_sent_video(monkeypatch, managed_bot):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        video=SimpleNamespace(duration=12),
        answer=AsyncMock(),
    )
    bot = managed_bot(status=ManagedBotStatus.ACTIVE, remaining_seconds=48)
    monkeypatch.setattr(routes.managed_bots_repository, "get_by_telegram_bot_id", Mock(return_value=bot))
    consume = Mock(return_value=(VideoLimitConsumption.CONSUMED, bot))
    monkeypatch.setattr(routes.managed_bots_repository, "consume_video_limit", consume)

    assert asyncio.run(routes.process_managed_bot_message(message, 99, 12)) == {"status": "consumed"}
    consume.assert_called_once_with(bot.id, 12, 12)
    message.answer.assert_awaited_once()


def test_register_managed_bot_only_accepts_owner_and_prepares_record(monkeypatch, managed_bot):
    record = managed_bot(telegram_bot_id=99)
    register = Mock(return_value=record)
    prepare = Mock(return_value=record)
    monkeypatch.setattr(routes.admin_bot_settings, "owner_id", 7)
    monkeypatch.setattr(routes.managed_bots_repository, "register_created_bot", register)
    monkeypatch.setattr(routes.activation_service, "prepare_activation", prepare)
    bot = SimpleNamespace(send_message=AsyncMock())

    foreign = SimpleNamespace(user=SimpleNamespace(id=8), bot_user=SimpleNamespace(id=99, username="personal_bot", first_name="Personal"))
    asyncio.run(routes.register_managed_bot(foreign, bot))
    register.assert_not_called()

    event = SimpleNamespace(user=SimpleNamespace(id=7), bot_user=SimpleNamespace(id=99, username="personal_bot", first_name="Personal"))
    asyncio.run(routes.register_managed_bot(event, bot))
    register.assert_called_once_with(99, "personal_bot", "Personal")
    prepare.assert_called_once_with(record.id)
    bot.send_message.assert_awaited_once()
