import re
import secrets
from dataclasses import replace

from bot_factories.admin_bot.db.managed_bots import (
    ActivationResult,
    ManagedBotAccessMode,
    ManagedBotRow,
    ManagedBotStatus,
)
from bot_factories.admin_bot.telegram_api import ManagedBotTelegramApi
from bot_factories.admin_bot.repositories.managed_bots import ManagedBotsRepository


class ManagedBotActivationService:
    def __init__(
        self,
        repository: ManagedBotsRepository,
        telegram_api: ManagedBotTelegramApi,
    ) -> None:
        self.repository = repository
        self.telegram_api = telegram_api

    def prepare_activation(self, bot_id: int) -> ManagedBotRow:
        bot = self._require_bot(bot_id)
        if bot.status == ManagedBotStatus.ACTIVE:
            return bot
        if bot.telegram_bot_id is None:
            raise ValueError("Managed bot has not been created in Telegram")

        token = bot.child_bot_token
        claim_token = bot.claim_token or secrets.token_urlsafe(24)
        try:
            if not token:
                token = self.telegram_api.get_managed_bot_token(bot.telegram_bot_id)
            self.telegram_api.configure_child_webhook(token, bot.telegram_bot_id)
            self.telegram_api.set_access_open(bot.telegram_bot_id)
        except RuntimeError as error:
            return self.repository.save(
                replace(
                    bot,
                    child_bot_token=token,
                    claim_token=claim_token,
                    status=ManagedBotStatus.ERROR,
                    activation_error=_sanitize_error(str(error)),
                )
            )

        return self.repository.save(
            replace(
                bot,
                child_bot_token=token,
                claim_token=claim_token,
                status=ManagedBotStatus.AWAITING_ACTIVATION,
                access_mode=None,
                activation_error=None,
            )
        )

    def recover_activation(self, bot_id: int) -> ManagedBotRow:
        bot = self._require_bot(bot_id)
        if bot.status == ManagedBotStatus.ACTIVE:
            return bot
        return self.prepare_activation(bot_id)

    @staticmethod
    def activation_link(bot: ManagedBotRow) -> str | None:
        if bot.telegram_bot_id is None or not bot.claim_token:
            return None
        return f"https://t.me/{bot.username}?start=claim_{bot.claim_token}"

    def handle_claim(
        self,
        *,
        telegram_bot_id: int,
        update_id: int,
        command_text: str | None,
        claimant_id: int | None,
        claimant_username: str | None,
        claimant_name: str | None,
    ) -> ActivationResult:
        bot = self.repository.get_by_telegram_bot_id(telegram_bot_id)
        if bot is None or bot.claim_token is None:
            return ActivationResult.IGNORED
        if (
            bot.claim_webhook_update_id is not None
            and update_id <= bot.claim_webhook_update_id
        ):
            return ActivationResult.DUPLICATE

        token = _claim_token(command_text)
        if (
            token is None
            or not secrets.compare_digest(bot.claim_token, token)
            or not isinstance(claimant_id, int)
            or claimant_id <= 0
        ):
            self.repository.save(replace(bot, claim_webhook_update_id=update_id))
            return ActivationResult.INVALID

        pending = replace(
            bot,
            recipient_id=claimant_id,
            recipient_username=claimant_username,
            recipient_name=claimant_name,
            claim_webhook_update_id=update_id,
        )
        try:
            self.telegram_api.restrict_access(telegram_bot_id, claimant_id)
            settings = self.telegram_api.get_access_settings(telegram_bot_id)
            added_ids = {
                user.get("id")
                for user in settings.get("added_users", [])
                if isinstance(user, dict)
            }
            if (
                settings.get("is_access_restricted") is True
                and claimant_id in added_ids
            ):
                self.repository.save(
                    replace(
                        pending,
                        status=ManagedBotStatus.ACTIVE,
                        claim_token=None,
                        access_mode=ManagedBotAccessMode.TELEGRAM,
                        activation_error=None,
                    )
                )
                return ActivationResult.CONFIGURED

            self.telegram_api.set_access_open(telegram_bot_id)
            reopened = self.telegram_api.get_access_settings(telegram_bot_id)
            if reopened.get("is_access_restricted") is False:
                self.repository.save(
                    replace(
                        pending,
                        status=ManagedBotStatus.ACTIVE,
                        claim_token=None,
                        access_mode=ManagedBotAccessMode.APPLICATION,
                        activation_error=None,
                    )
                )
                return ActivationResult.CONFIGURED
        except RuntimeError as error:
            self.repository.save(
                replace(
                    pending,
                    status=ManagedBotStatus.ERROR,
                    activation_error=_sanitize_error(str(error)),
                )
            )
            return ActivationResult.BLOCKED

        self.repository.save(
            replace(
                pending,
                status=ManagedBotStatus.ERROR,
                activation_error="Telegram access settings could not be verified",
            )
        )
        return ActivationResult.FAILED

    @staticmethod
    def is_recipient_allowed(bot: ManagedBotRow, telegram_user_id: int | None) -> bool:
        return (
            bot.status == ManagedBotStatus.ACTIVE
            and isinstance(telegram_user_id, int)
            and telegram_user_id > 0
            and telegram_user_id == bot.recipient_id
        )

    def _require_bot(self, bot_id: int) -> ManagedBotRow:
        bot = self.repository.get_bot(bot_id)
        if bot is None:
            raise LookupError(f"Managed bot {bot_id} was not found")
        return bot


def _claim_token(command_text: str | None) -> str | None:
    parts = (command_text or "").strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].split("@", 1)[0] != "/start":
        return None
    token = parts[1]
    return token[len("claim_") :] if token.startswith("claim_") else None


def _sanitize_error(error: str) -> str:
    value = re.sub(
        r"(?:https?://|tg://)\S+|\b\d{5,}:[A-Za-z0-9_-]+|claim_[A-Za-z0-9_-]+",
        "[redacted]",
        error,
    )
    return value[:250]
