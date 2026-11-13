from dataclasses import replace

import pytest

from bot_factories.admin_bot.db.managed_bots import ManagedBotRow, ManagedBotStatus


@pytest.fixture
def managed_bot():
    def create(**changes):
        return replace(
            ManagedBotRow(
                id=1,
                telegram_bot_id=99,
                username="personal_bot",
                name="Personal bot",
                recipient_id=7,
                recipient_username="recipient",
                recipient_name="Recipient",
                remaining_seconds=60,
                status=ManagedBotStatus.AWAITING_ACTIVATION,
            ),
            **changes,
        )

    return create
