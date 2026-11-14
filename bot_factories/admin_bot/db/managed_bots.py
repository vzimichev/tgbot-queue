import sys
from shared.managed_bots.db import managed_bots as _implementation
sys.modules[__name__] = _implementation
