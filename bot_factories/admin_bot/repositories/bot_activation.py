import sys
from shared.managed_bots.repositories import bot_activation as _implementation
sys.modules[__name__] = _implementation
