import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bot_factories.managed_bots.managed import routes as routes
from bot_factories.managed_bots.shared.db.managed_bots import (
    ActivationResult,
    ManagedBotStatus,
)
from bot_factories.managed_bots.shared.managed_bot_transactions import (
    ManagedBotVideoCharge,
    ManagedBotVideoChargeResult,
)


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

    assert asyncio.run(routes.process_managed_bot_message(message, 99, 12)) == {
        "status": "ignored"
    }


def test_active_managed_bot_charges_the_sent_video(monkeypatch, managed_bot):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        video=SimpleNamespace(duration=12),
        answer=AsyncMock(),
    )
    bot = managed_bot(status=ManagedBotStatus.ACTIVE, remaining_seconds=48)
    monkeypatch.setattr(
        routes.managed_bots_repository, "get_by_telegram_bot_id", Mock(return_value=bot)
    )
    charge_video = Mock(
        return_value=ManagedBotVideoCharge(ManagedBotVideoChargeResult.CONSUMED, 48)
    )
    monkeypatch.setattr(
        routes.managed_bot_transactions_repository, "charge_video", charge_video
    )

    assert asyncio.run(routes.process_managed_bot_message(message, 99, 12)) == {
        "status": "consumed"
    }
    charge_video.assert_called_once_with(99, 7, 12, 12)
    message.answer.assert_awaited_once()


def test_managed_bot_balance_command_shows_the_recipient_balance(monkeypatch):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        answer=AsyncMock(),
    )
    account = SimpleNamespace(
        result=routes.ManagedBotAccountResult.AVAILABLE,
        remaining_seconds=48,
    )
    get_account = Mock(return_value=account)
    monkeypatch.setattr(
        routes.managed_bots_repository, "get_managed_bot_account", get_account
    )

    assert asyncio.run(routes.show_managed_bot_balance(message, 99)) == {
        "status": "balance"
    }
    get_account.assert_called_once_with(99, 7)
    message.answer.assert_awaited_once_with("Remaining limit: 48 seconds.")


def test_managed_bot_transactions_command_lists_ledger_entries(monkeypatch):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        answer=AsyncMock(),
    )
    transaction = SimpleNamespace(
        created_at=__import__("datetime").datetime(2026, 10, 12, 10, 30),
        transaction_type=routes.TransactionType.TOP_UP,
        seconds=60,
    )
    account = SimpleNamespace(
        result=routes.ManagedBotAccountResult.AVAILABLE,
        remaining_seconds=108,
        transactions=(transaction,),
    )
    monkeypatch.setattr(
        routes.managed_bots_repository,
        "get_managed_bot_account",
        Mock(return_value=account),
    )

    assert asyncio.run(routes.show_managed_bot_transactions(message, 99)) == {
        "status": "transactions"
    }
    assert "Limit added: +60 seconds" in message.answer.await_args.args[0]
