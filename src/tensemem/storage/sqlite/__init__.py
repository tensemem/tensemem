"""SQLite storage backend (default)."""

from tensemem.storage.sqlite.connection import SqliteCapabilityError, connect
from tensemem.storage.sqlite.database import SqliteDatabase
from tensemem.storage.sqlite.migrate import apply_migrations

__all__ = [
    "SqliteCapabilityError",
    "SqliteDatabase",
    "apply_migrations",
    "connect",
]
