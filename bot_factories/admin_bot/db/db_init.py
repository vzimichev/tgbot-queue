import sys
from shared.managed_bots.db import db_init as _implementation
sys.modules[__name__] = _implementation
