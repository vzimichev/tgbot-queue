import sys
from shared.managed_bots.repositories import managed_bot_transactions as _implementation
sys.modules[__name__] = _implementation
