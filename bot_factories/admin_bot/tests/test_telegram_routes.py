import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bot_factories.admin_bot import routes as admin_routes


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
