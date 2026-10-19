"""Encode and parse ``explicit_op`` episode content written by ``Memory._commit``."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, cast

from tensemem.core.models import ExtractedOp, OpKind
from tensemem.core.normalize import normalize_key


def format_explicit_ops(
    ops: Sequence[ExtractedOp],
    *,
    note: str | None = None,
) -> str:
    """JSON list of ops so values may contain ``;`` without breaking replay."""
    items: list[dict[str, str]] = [
        {
            "op": op.op.value,
            "subject": op.subject,
            "predicate": op.predicate,
            "object": op.object,
        }
        for op in ops
    ]
    if note:
        items.append({"op": "NOTE", "object": note})
    return json.dumps(items, separators=(",", ":"), ensure_ascii=False)


def parse_explicit_ops(content: str) -> tuple[ExtractedOp, ...]:
    """Parse JSON explicit ops, or the legacy ``SET user.p=v; ...`` text form.

    ``DENY`` and ``NOTE`` entries are skipped so correction episodes stay in the
    log without being re-applied as facts. Rejected claims block the denied
    value on rebuild.
    """
    stripped = content.lstrip()
    if stripped.startswith("["):
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            return ()
        if isinstance(loaded, list):
            return _from_json_items(cast(list[object], loaded))
        return ()
    return _from_legacy(content)


def _from_json_items(items: Sequence[object]) -> tuple[ExtractedOp, ...]:
    ops: list[ExtractedOp] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = cast(dict[str, Any], item)
        kind = _op_kind(str(row.get("op", "")))
        if kind is None:
            continue
        subject = str(row.get("subject", "")).strip()
        predicate = str(row.get("predicate", "")).strip()
        if not subject or not predicate:
            continue
        ops.append(
            ExtractedOp(
                subject=subject,
                predicate=normalize_key(predicate),
                object=str(row.get("object", "")),
                op=kind,
                evidence=kind.value,
            )
        )
    return tuple(ops)


def _from_legacy(content: str) -> tuple[ExtractedOp, ...]:
    ops: list[ExtractedOp] = []
    for chunk in content.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        kind_s, _, rest = chunk.partition(" ")
        kind = _op_kind(kind_s)
        if kind is None:
            continue
        subject_pred, sep, value = rest.partition("=")
        if not sep:
            continue
        subject, dot, predicate = subject_pred.rpartition(".")
        if not dot or not subject.strip() or not predicate.strip():
            continue
        ops.append(
            ExtractedOp(
                subject=subject.strip(),
                predicate=normalize_key(predicate),
                object=value,
                op=kind,
                evidence=chunk,
            )
        )
    return tuple(ops)


def _op_kind(name: str) -> OpKind | None:
    try:
        kind = OpKind(name)
    except ValueError:
        return None
    if kind is OpKind.DENY:
        return None
    return kind
