from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tensemem.storage.sqlite.connection import connect, resolve_uri


def test_read_only_rejects_writable_file_uri(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    uri = f"file:{path.as_posix()}?mode=rwc"
    with pytest.raises(ValueError, match="writable"):
        resolve_uri(uri, read_only=True)
    with pytest.raises(ValueError, match="writable"):
        connect(uri, read_only=True)
    assert not path.exists()


def test_read_only_file_uri_does_not_create(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    uri = resolve_uri(f"file:{path.as_posix()}", read_only=True)
    assert "mode=ro" in uri
    with pytest.raises(sqlite3.OperationalError):
        connect(f"file:{path.as_posix()}", read_only=True)
    assert not path.exists()


def test_shared_memory_uri_keeps_memory_mode() -> None:
    uri = "file:probe?mode=memory&cache=shared"
    assert resolve_uri(uri, read_only=True) == uri
