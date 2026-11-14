import sys
from shared.managed_bots import telegram_api as _implementation
sys.modules[__name__] = _implementation
