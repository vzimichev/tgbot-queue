import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, TypeVar
from pathlib import Path

from bot_factories.admin_bot.db.db_init import initialize


database_path = Path(__file__).resolve().parents[1] / ".cache" / "admin.sqlite3"
Result = TypeVar("Result")


def connect() -> sqlite3.Connection:
    database_path.parent.mkdir(mode=0o700, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    initialize(connection)
    return connection


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def transactional(operation: Callable[..., Result]) -> Callable[..., Result]:
    @wraps(operation)
    def wrapped(*args: Any, **kwargs: Any) -> Result:
        if "connection" in kwargs:
            raise TypeError("connection is managed by @transactional")
        with transaction() as connection:
            return operation(*args, connection=connection, **kwargs)

    return wrapped
