from bot_factories.admin_bot.repositories.bot_activation import (
    ManagedBotActivationService,
)
from bot_factories.admin_bot.repositories.bot_manager import ManagedBotsRepository
from bot_factories.admin_bot.repositories.managed_bot_transactions import (
    ManagedBotTransactionsRepository,
)
from bot_factories.admin_bot.telegram_api import ManagedBotTelegramApi


managed_bots_repository = ManagedBotsRepository()
managed_bot_transactions_repository = ManagedBotTransactionsRepository()
activation_service = ManagedBotActivationService(
    managed_bots_repository,
    ManagedBotTelegramApi(),
)
