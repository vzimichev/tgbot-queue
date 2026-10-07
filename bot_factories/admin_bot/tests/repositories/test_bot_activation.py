from dataclasses import replace

from bot_factories.admin_bot.repositories.bot_activation import (
    ManagedBotActivationService,
)
from bot_factories.admin_bot.db.managed_bots import (
    ActivationResult,
    ManagedBotAccessMode,
    ManagedBotRow,
    ManagedBotStatus,
)


class Repository:
    def __init__(self, bot):
        self.bot = bot

    def get_bot(self, bot_id):
        return self.bot if self.bot.id == bot_id else None

    def get_by_telegram_bot_id(self, telegram_bot_id):
        return self.bot if self.bot.telegram_bot_id == telegram_bot_id else None

    def save(self, bot):
        self.bot = bot
        return bot


class TelegramApi:
    def __init__(self, settings=None, error=None):
        self.settings = settings or {
            "is_access_restricted": True,
            "added_users": [{"id": 42}],
        }
        self.error = error
        self.calls = []

    def get_managed_bot_token(self, _):
        return "child-token"

    def configure_child_webhook(self, *_):
        self.calls.append("webhook")

    def set_access_open(self, *_):
        self.calls.append("open")
        if self.error:
            raise RuntimeError(self.error)

    def restrict_access(self, *_):
        self.calls.append("restrict")

    def get_access_settings(self, _):
        return self.settings


def bot(**changes):
    return replace(
        ManagedBotRow(
            id=1,
            telegram_bot_id=99,
            username="personal_bot",
            name="Personal bot",
            recipient_id=7,
            recipient_username="selected",
            recipient_name="Selected",
            remaining_seconds=60,
            status=ManagedBotStatus.AWAITING_ACTIVATION,
        ),
        **changes,
    )


def test_prepare_activation_creates_link_state():
    repo = Repository(bot())
    service = ManagedBotActivationService(repo, TelegramApi())

    prepared = service.prepare_activation(1)

    assert prepared.child_bot_token == "child-token"
    assert prepared.claim_token
    assert prepared.status == ManagedBotStatus.AWAITING_ACTIVATION
    assert service.activation_link(prepared).endswith(prepared.claim_token)


def test_claim_uses_actual_holder_and_is_one_time():
    repo = Repository(bot(child_bot_token="child", claim_token="secret"))
    service = ManagedBotActivationService(repo, TelegramApi())

    result = service.handle_claim(
        telegram_bot_id=99,
        update_id=10,
        command_text="/start claim_secret",
        claimant_id=42,
        claimant_username="holder",
        claimant_name="Holder",
    )

    assert result == ActivationResult.CONFIGURED
    assert repo.bot.status == ManagedBotStatus.ACTIVE
    assert repo.bot.access_mode == ManagedBotAccessMode.TELEGRAM
    assert repo.bot.recipient_id == 42
    assert repo.bot.claim_token is None
    assert (
        service.handle_claim(
            telegram_bot_id=99,
            update_id=11,
            command_text="/start claim_secret",
            claimant_id=42,
            claimant_username="holder",
            claimant_name="Holder",
        )
        == ActivationResult.IGNORED
    )


def test_unverified_telegram_access_uses_application_guard():
    repo = Repository(bot(child_bot_token="child", claim_token="secret"))
    api = TelegramApi({"is_access_restricted": False, "added_users": []})
    service = ManagedBotActivationService(repo, api)

    result = service.handle_claim(
        telegram_bot_id=99,
        update_id=10,
        command_text="/start claim_secret",
        claimant_id=42,
        claimant_username=None,
        claimant_name="Holder",
    )

    assert result == ActivationResult.CONFIGURED
    assert repo.bot.access_mode == ManagedBotAccessMode.APPLICATION
    assert service.is_recipient_allowed(repo.bot, 42)
    assert not service.is_recipient_allowed(repo.bot, 7)


def test_invalid_claim_does_not_consume_token():
    repo = Repository(bot(child_bot_token="child", claim_token="secret"))
    service = ManagedBotActivationService(repo, TelegramApi())

    assert (
        service.handle_claim(
            telegram_bot_id=99,
            update_id=10,
            command_text="/start claim_wrong",
            claimant_id=42,
            claimant_username=None,
            claimant_name=None,
        )
        == ActivationResult.INVALID
    )
    assert repo.bot.claim_token == "secret"


def test_prepare_failure_keeps_recovery_state_and_redacts_credentials():
    repo = Repository(bot(telegram_bot_id=99))
    api = TelegramApi(error="request failed for claim_secret and 123456:token")
    service = ManagedBotActivationService(repo, api)

    prepared = service.prepare_activation(1)

    assert prepared.status == ManagedBotStatus.ERROR
    assert prepared.claim_token
    assert prepared.child_bot_token == "child-token"
    assert "claim_secret" not in prepared.activation_error
    assert "123456:token" not in prepared.activation_error
    assert "[redacted]" in prepared.activation_error


def test_active_bot_is_not_reconfigured_during_recovery():
    repo = Repository(bot(status=ManagedBotStatus.ACTIVE))
    api = TelegramApi()
    service = ManagedBotActivationService(repo, api)

    recovered = service.recover_activation(1)

    assert recovered == repo.bot
    assert api.calls == []


def test_duplicate_claim_update_does_not_change_activation():
    original = bot(
        child_bot_token="child",
        claim_token="secret",
        claim_webhook_update_id=10,
    )
    repo = Repository(original)
    service = ManagedBotActivationService(repo, TelegramApi())

    result = service.handle_claim(
        telegram_bot_id=99,
        update_id=10,
        command_text="/start claim_secret",
        claimant_id=42,
        claimant_username="holder",
        claimant_name="Holder",
    )

    assert result == ActivationResult.DUPLICATE
    assert repo.bot == original
