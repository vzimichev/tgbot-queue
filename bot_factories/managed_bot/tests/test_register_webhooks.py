from unittest.mock import Mock

from bot_factories.admin_bot.db.managed_bots import ManagedBotStatus
from bot_factories.admin_bot.register_webhooks import register_existing_webhooks


def test_registers_persisted_and_retrieved_tokens_without_logging_them(managed_bot, capsys):
    persisted = managed_bot(id=1, child_bot_token="persisted-token")
    retrieved = managed_bot(id=2, child_bot_token=None, telegram_bot_id=100)
    repository = Mock()
    repository.list_bots.return_value = [persisted, retrieved]
    telegram_api = Mock()
    telegram_api.get_managed_bot_token.return_value = "retrieved-token"

    summary = register_existing_webhooks(repository, telegram_api)

    assert summary.registered == 2
    assert summary.skipped == 0
    assert summary.failed == 0
    telegram_api.configure_child_webhook.assert_any_call("persisted-token", 99)
    telegram_api.configure_child_webhook.assert_any_call("retrieved-token", 100)
    output = capsys.readouterr().out
    assert "persisted-token" not in output
    assert "retrieved-token" not in output


def test_skips_pending_bots_and_supports_dry_run(managed_bot, capsys):
    pending = managed_bot(
        id=1,
        telegram_bot_id=None,
        status=ManagedBotStatus.PENDING_CREATION,
    )
    active = managed_bot(id=2, telegram_bot_id=100, child_bot_token="secret")
    repository = Mock()
    repository.list_bots.return_value = [pending, active]
    telegram_api = Mock()

    summary = register_existing_webhooks(repository, telegram_api, dry_run=True)

    assert summary.registered == 1
    assert summary.skipped == 1
    assert summary.failed == 0
    telegram_api.configure_child_webhook.assert_not_called()
    assert "secret" not in capsys.readouterr().out


def test_reports_failures_without_stopping_other_bots(managed_bot):
    first = managed_bot(id=1, telegram_bot_id=100, child_bot_token="first")
    second = managed_bot(id=2, telegram_bot_id=101, child_bot_token="second")
    repository = Mock()
    repository.list_bots.return_value = [first, second]
    telegram_api = Mock()
    telegram_api.configure_child_webhook.side_effect = [
        RuntimeError("first failed"),
        None,
    ]

    summary = register_existing_webhooks(repository, telegram_api)

    assert summary.registered == 1
    assert summary.failed == 1
    assert telegram_api.configure_child_webhook.call_count == 2
