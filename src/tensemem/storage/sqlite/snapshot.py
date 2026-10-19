"""Load the resolver snapshot and public fact views from SQLite."""

from __future__ import annotations

import sqlite3

from tensemem.core.models import (
    Cardinality,
    FactStatus,
    FactView,
    Freshness,
    Modality,
    Scope,
    ValidPrecision,
)
from tensemem.core.resolver import FactSnap, RejectedClaim, Snapshot
from tensemem.storage.sqlite.entities import SELF_NAME

FACT_SELECT = """
SELECT
  f.id,
  f.public_id,
  f.object_text,
  f.object_norm,
  f.confidence,
  f.valid_from,
  f.valid_to,
  f.valid_precision,
  f.status,
  f.modality,
  f.recorded_at,
  f.recorded_seq,
  f.superseded_by,
  p.name AS predicate,
  p.cardinality AS cardinality,
  p.pinned AS pinned,
  e.kind AS subject_kind,
  e.canonical_name AS subject_name
FROM facts f
JOIN predicates p ON p.id = f.predicate_id
JOIN entities e ON e.id = f.subject_id
"""


def load_snapshot(conn: sqlite3.Connection, scope: Scope, *, episode_seq: int) -> Snapshot:
    """ACTIVE facts and rejected claims for ``resolve()``."""
    fact_rows = conn.execute(
        FACT_SELECT + " WHERE f.scope_id = ? AND f.status = 'ACTIVE' ORDER BY f.id",
        (scope.id,),
    ).fetchall()
    claim_rows = conn.execute(
        """
        SELECT
          e.kind AS subject_kind,
          e.canonical_name AS subject_name,
          p.name AS predicate,
          r.object_norm,
          r.until_seq
        FROM rejected_claims r
        JOIN entities e ON e.id = r.subject_id
        JOIN predicates p ON p.id = r.predicate_id
        WHERE r.scope_id = ?
        """,
        (scope.id,),
    ).fetchall()
    return Snapshot(
        facts=tuple(
            FactSnap(
                id=row["public_id"],
                subject=_subject_name(row),
                predicate=row["predicate"],
                object_norm=row["object_norm"],
                confidence=float(row["confidence"]),
                valid_from=row["valid_from"],
                valid_precision=ValidPrecision(row["valid_precision"]),
                status=FactStatus.ACTIVE,
            )
            for row in fact_rows
        ),
        rejected_claims=tuple(
            RejectedClaim(
                subject=_subject_name(row),
                predicate=row["predicate"],
                object_norm=row["object_norm"],
                until_seq=int(row["until_seq"]),
            )
            for row in claim_rows
        ),
        episode_seq=episode_seq,
    )


def list_facts(
    conn: sqlite3.Connection,
    scope_id: int,
    *,
    statuses: tuple[FactStatus, ...],
    predicate: str | None = None,
) -> list[FactView]:
    sql = FACT_SELECT + " WHERE f.scope_id = ? AND f.status IN ({})".format(
        ",".join("?" * len(statuses))
    )
    params: list[object] = [scope_id, *[status.value for status in statuses]]
    if predicate is not None:
        sql += " AND p.name = ?"
        params.append(predicate)
    sql += " ORDER BY p.name, f.recorded_seq, f.id"
    rows = conn.execute(sql, params).fetchall()
    return [_to_view(row) for row in rows]


def load_fact_view(conn: sqlite3.Connection, public_id: str) -> sqlite3.Row | None:
    return conn.execute(FACT_SELECT + " WHERE f.public_id = ?", (public_id,)).fetchone()


def freshness_for(conn: sqlite3.Connection, scope: Scope | None) -> Freshness:
    if scope is None:
        return Freshness(as_of_seq=0, latest_seq=0, pending=0, failed=0)
    latest = conn.execute(
        "SELECT COALESCE(MAX(id), 0) AS n FROM episodes WHERE scope_id = ?",
        (scope.id,),
    ).fetchone()
    pending = conn.execute(
        "SELECT COUNT(*) AS n FROM episodes WHERE scope_id = ? AND status = 'PENDING'",
        (scope.id,),
    ).fetchone()
    failed = conn.execute(
        "SELECT COUNT(*) AS n FROM episodes WHERE scope_id = ? AND status = 'FAILED'",
        (scope.id,),
    ).fetchone()
    return Freshness(
        as_of_seq=scope.applied_seq,
        latest_seq=int(latest["n"]),
        pending=int(pending["n"]),
        failed=int(failed["n"]),
        projection_version=scope.projection_version,
    )


def to_fact_view(row: sqlite3.Row) -> FactView:
    return _to_view(row)


def _to_view(row: sqlite3.Row) -> FactView:
    return FactView(
        id=row["public_id"],
        subject=_subject_name(row),
        predicate=row["predicate"],
        object=row["object_text"],
        status=FactStatus(row["status"]),
        modality=Modality(row["modality"]),
        confidence=float(row["confidence"]),
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        valid_precision=ValidPrecision(row["valid_precision"]),
        recorded_at=row["recorded_at"],
        recorded_seq=int(row["recorded_seq"]),
        cardinality=Cardinality(row["cardinality"]),
        pinned=bool(row["pinned"]),
    )


def _subject_name(row: sqlite3.Row) -> str:
    if row["subject_kind"] == "self":
        return SELF_NAME
    return str(row["subject_name"])
