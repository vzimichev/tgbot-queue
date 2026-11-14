import sys
from shared.managed_bots.repositories import bot_manager as _implementation
sys.modules[__name__] = _implementation
