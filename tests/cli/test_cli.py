from datetime import UTC, datetime
from pathlib import Path

import pytest

from tensemem import Memory
from tensemem.cli import main
from tensemem.core.clock import FrozenClock


def test_inspect_history_explain_search_jobs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "t.db"
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(db, clock=clock) as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Delhi")
        fact_id = mem.state(user_id="u1").facts[0].id

    assert main(["--db", str(db), "inspect", "--user", "u1"]) == 0
    out = capsys.readouterr().out
    assert "Delhi" in out
    assert "lives_in" in out

    assert main(["--db", str(db), "history", "--user", "u1", "lives_in"]) == 0
    assert "Delhi" in capsys.readouterr().out

    assert main(["--db", str(db), "explain", fact_id]) == 0
    assert fact_id in capsys.readouterr().out

    assert main(["--db", str(db), "search", "--user", "u1", "live"]) == 0
    search_out = capsys.readouterr().out
    assert "Delhi" in search_out or "lives_in" in search_out

    assert main(["--db", str(db), "jobs", "--user", "u1"]) == 0
    assert "no jobs" in capsys.readouterr().out

    assert main(["--db", str(db), "freshness", "--user", "u1"]) == 0
    assert "current=True" in capsys.readouterr().out

    assert main(["--db", str(db), "stats", "--user", "u1"]) == 0
    assert "facts=1" in capsys.readouterr().out


def test_export_import_backup_via_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "src.db"
    dump = tmp_path / "u1.jsonl"
    copy = tmp_path / "copy.db"
    dest = tmp_path / "other.db"
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(db, clock=clock) as mem:
        mem.register_predicate("lives_in")
        mem.set(user_id="u1", predicate="lives_in", value="Pune")

    assert main(["--db", str(db), "export", "--user", "u1", "--out", str(dump)]) == 0
    assert dump.read_text(encoding="utf-8")
    assert main(["--db", str(dest), "import", "--user", "u1", str(dump)]) == 0
    assert "imported" in capsys.readouterr().out
    assert main(["--db", str(dest), "inspect", "--user", "u1"]) == 0
    assert "Pune" in capsys.readouterr().out

    assert main(["--db", str(db), "backup", str(copy)]) == 0
    with Memory(copy) as restored:
        assert restored.state(user_id="u1").values == {"lives_in": "Pune"}
