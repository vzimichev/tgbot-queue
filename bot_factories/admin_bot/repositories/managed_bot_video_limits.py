from dataclasses import dataclass
from enum import StrEnum

from bot_factories.admin_bot.db.managed_bot_limit_transactions import (
    VideoLimitConsumption,
)
from bot_factories.admin_bot.db.managed_bots import ManagedBotStatus
from bot_factories.admin_bot.repositories.managed_bot_limits import (
    ManagedBotLimitsRepository,
)
from bot_factories.admin_bot.repositories.managed_bots import ManagedBotsRepository


class ManagedBotVideoLimitResult(StrEnum):
    CONSUMED = "consumed"
    DUPLICATE = "duplicate"
    INSUFFICIENT = "insufficient"
    INACTIVE = "inactive"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class ManagedBotVideoLimitCharge:
    result: ManagedBotVideoLimitResult
    remaining_seconds: int | None = None


class ManagedBotVideoLimitsRepository:
    """Use case for charging a personal bot's incoming video."""

    def __init__(
        self,
        managed_bots: ManagedBotsRepository | None = None,
        limits: ManagedBotLimitsRepository | None = None,
    ) -> None:
        self.managed_bots = managed_bots or ManagedBotsRepository()
        self.limits = limits or ManagedBotLimitsRepository()

    def charge_video(
        self,
        telegram_bot_id: int,
        telegram_user_id: int,
        update_id: int,
        duration_seconds: int,
    ) -> ManagedBotVideoLimitCharge:
        bot = self.managed_bots.get_by_telegram_bot_id(telegram_bot_id)
        if bot is None or bot.status != ManagedBotStatus.ACTIVE:
            return ManagedBotVideoLimitCharge(ManagedBotVideoLimitResult.INACTIVE)
        if bot.recipient_id != telegram_user_id:
            return ManagedBotVideoLimitCharge(ManagedBotVideoLimitResult.FORBIDDEN)

        result, balance = self.limits.consume_video_limit(
            bot.id, update_id, duration_seconds
        )
        return ManagedBotVideoLimitCharge(
            ManagedBotVideoLimitResult(result), balance
        )
