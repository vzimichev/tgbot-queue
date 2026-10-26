import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bot_factories.admin_bot.routes import admin_bot as admin_routes
from bot_factories.admin_bot.routes import managed_bot as routes
from bot_factories.admin_bot.db.managed_bots import ActivationResult, ManagedBotStatus
from bot_factories.admin_bot.repositories.managed_bot_transactions import (
    ManagedBotVideoCharge,
    ManagedBotVideoChargeResult,
)


def test_parse_seconds_accepts_only_positive_ascii_integers():
    assert admin_routes._parse_seconds(" 10 ") == 10
    for value in (None, "", "0", "-1", "1.5", "²"):
        assert admin_routes._parse_seconds(value) is None


def test_is_owner_rejects_groups_and_other_users(monkeypatch):
    monkeypatch.setattr(admin_routes.admin_bot_settings, "owner_id", 7)

    def event(user_id, chat_id):
        return SimpleNamespace(
            from_user=SimpleNamespace(id=user_id),
            message=SimpleNamespace(chat=SimpleNamespace(id=chat_id)),
        )

    assert admin_routes.is_owner(event(7, 7))
    assert not admin_routes.is_owner(event(8, 8))
    assert not admin_routes.is_owner(event(7, -7))


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


def test_faceswap_command_checks_access_and_starts_media_flow(monkeypatch):
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())
    account = SimpleNamespace(result=routes.ManagedBotAccountResult.AVAILABLE)
    monkeypatch.setattr(
        routes.managed_bots_repository,
        "get_managed_bot_account",
        Mock(return_value=account),
    )

    assert asyncio.run(routes.begin_managed_faceswap(message, state, 99)) == {
        "status": "awaiting_media"
    }
    state.clear.assert_awaited_once()
    state.set_state.assert_awaited_once_with(
        routes.ManagedFaceSwapFlow.WAITING_FOR_MEDIA
    )
    assert "one photo and one video" in message.answer.await_args.args[0]


def test_faceswap_photo_waits_for_video_without_charging(monkeypatch):
    stored = {}

    async def update_data(**values):
        stored.update(values)

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        bot=SimpleNamespace(token="123:child"),
        chat=SimpleNamespace(id=7),
        photo=[SimpleNamespace(file_id="photo-id", file_unique_id="photo")],
        video=None,
        document=None,
        media_group_id=None,
        answer=AsyncMock(),
    )
    state = SimpleNamespace(
        clear=AsyncMock(),
        get_data=AsyncMock(side_effect=lambda: stored.copy()),
        update_data=update_data,
    )
    account = SimpleNamespace(result=routes.ManagedBotAccountResult.AVAILABLE)
    monkeypatch.setattr(
        routes.managed_bots_repository,
        "get_managed_bot_account",
        Mock(return_value=account),
    )
    charge_video = Mock()
    monkeypatch.setattr(
        routes.managed_bot_transactions_repository, "charge_video", charge_video
    )

    assert asyncio.run(
        routes.receive_managed_faceswap_media(message, state, 99, 12)
    ) == {"status": "awaiting_media"}
    assert stored["photo_file_id"] == "photo-id"
    charge_video.assert_not_called()


def test_faceswap_charges_duration_of_video_received_before_photo(monkeypatch):
    stored = {
        "video_file_id": "video-id",
        "video_file_name": "target.mp4",
        "video_duration": 12,
    }

    async def update_data(**values):
        stored.update(values)

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        bot=SimpleNamespace(token="123:child"),
        chat=SimpleNamespace(id=7),
        photo=[SimpleNamespace(file_id="photo-id", file_unique_id="photo")],
        video=None,
        document=None,
        media_group_id=None,
        answer=AsyncMock(),
    )
    state = SimpleNamespace(
        clear=AsyncMock(),
        get_data=AsyncMock(side_effect=lambda: stored.copy()),
        update_data=update_data,
    )
    account = SimpleNamespace(result=routes.ManagedBotAccountResult.AVAILABLE)
    monkeypatch.setattr(
        routes.managed_bots_repository,
        "get_managed_bot_account",
        Mock(return_value=account),
    )
    charge_video = Mock(
        return_value=ManagedBotVideoCharge(ManagedBotVideoChargeResult.CONSUMED, 36)
    )
    monkeypatch.setattr(
        routes.managed_bot_transactions_repository, "charge_video", charge_video
    )
    enqueue = Mock()
    monkeypatch.setattr(routes.current_app, "send_task", enqueue)

    assert asyncio.run(
        routes.receive_managed_faceswap_media(message, state, 99, 13)
    ) == {"status": "queued"}
    charge_video.assert_called_once_with(99, 7, 13, 12)
    enqueue.assert_called_once()
    assert enqueue.call_args.args[0] == "managed_faceswap.process"
    assert enqueue.call_args.kwargs["queue"] == "faceswap_jobs"


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


def test_register_managed_bot_only_accepts_owner_and_prepares_record(
    monkeypatch, managed_bot
):
    record = managed_bot(telegram_bot_id=99)
    register = Mock(return_value=record)
    prepare = Mock(return_value=record)
    monkeypatch.setattr(admin_routes.admin_bot_settings, "owner_id", 7)
    monkeypatch.setattr(
        admin_routes.managed_bots_repository, "register_created_bot", register
    )
    monkeypatch.setattr(admin_routes.activation_service, "prepare_activation", prepare)
    bot = SimpleNamespace(send_message=AsyncMock())

    foreign = SimpleNamespace(
        user=SimpleNamespace(id=8),
        bot_user=SimpleNamespace(id=99, username="personal_bot", first_name="Personal"),
    )
    asyncio.run(admin_routes.register_managed_bot(foreign, bot))
    register.assert_not_called()

    event = SimpleNamespace(
        user=SimpleNamespace(id=7),
        bot_user=SimpleNamespace(id=99, username="personal_bot", first_name="Personal"),
    )
    asyncio.run(admin_routes.register_managed_bot(event, bot))
    register.assert_called_once_with(99, "personal_bot", "Personal")
    prepare.assert_called_once_with(record.id)
    bot.send_message.assert_awaited_once()
