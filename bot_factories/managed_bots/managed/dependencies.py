from bot_factories.managed_bots.shared.config import settings
from bot_factories.managed_bots.shared.bot_activation import (
    ManagedBotActivationService,
)
from bot_factories.managed_bots.shared.bot_manager import (
    ManagedBotsRepository,
)
from bot_factories.managed_bots.shared.managed_bot_transactions import (
    ManagedBotTransactionsRepository,
)
from bot_factories.managed_bots.shared.telegram_api import ManagedBotTelegramApi

managed_bots_repository = ManagedBotsRepository()
managed_bot_transactions_repository = ManagedBotTransactionsRepository()
activation_service = ManagedBotActivationService(
    managed_bots_repository,
    ManagedBotTelegramApi(
        admin_token=settings.token,
        child_webhook_url=settings.child_webhook_url,
        webhook_secret_token=settings.webhook_secret_token,
    ),
)
