import sys
from shared.managed_bots.db import db_engine as _implementation
sys.modules[__name__] = _implementation
