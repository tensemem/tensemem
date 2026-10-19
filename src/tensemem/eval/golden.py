"""Load labeled extract cases and score a provider (Day 18)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tensemem.core.models import Cardinality, ExtractedOp, OpKind
from tensemem.core.normalize import normalize_value
from tensemem.pipeline.extractor import extract
from tensemem.pipeline.guard import keep_ops
from tensemem.pipeline.snapshot import CompactFact, ExtractSnapshot, RegistryEntry
from tensemem.providers.llm.base import LLMProvider

_DEFAULT_REGISTRY = (
    RegistryEntry(name="lives_in", cardinality=Cardinality.ONE, description="city of residence"),
    RegistryEntry(
        name="uses_language",
        cardinality=Cardinality.MANY,
        description="programming languages",
    ),
    RegistryEntry(name="diet", cardinality=Cardinality.ONE, description="dietary constraint"),
)


class GoldOp(BaseModel):
    """One labeled operation. Evidence is not part of the match key."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = "user"
    predicate: str
    object: str
    op: OpKind = OpKind.SET


class GoldCase(BaseModel):
    """One labeled utterance plus the extract snapshot it should be scored against."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    category: str
    text: str
    reference_time: str = "2026-10-18"
    registry: tuple[RegistryEntry, ...] = ()
    facts: tuple[CompactFact, ...] = ()
    expected: tuple[GoldOp, ...] = ()
    skip_fake: bool = False


class CaseScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    category: str
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)


class Report(BaseModel):
    """Micro-averaged precision and recall, plus per-category rows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cases: int = Field(ge=0)
    skipped: int = Field(ge=0)
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)
    precision: float
    recall: float
    by_category: dict[str, tuple[float, float, int]]


def load_cases(path: Path) -> tuple[GoldCase, ...]:
    """Read JSONL cases. Blank lines are ignored."""
    rows: list[GoldCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(GoldCase.model_validate_json(line))
    return tuple(rows)


def op_key(subject: str, predicate: str, obj: str, op: OpKind) -> tuple[str, str, str, str]:
    return (subject, predicate, normalize_value(obj), op.value)


def score_ops(expected: Sequence[GoldOp], predicted: Sequence[ExtractedOp]) -> tuple[int, int, int]:
    """Return ``(tp, fp, fn)`` using set-match on subject, predicate, object, op."""
    want = {op_key(item.subject, item.predicate, item.object, item.op) for item in expected}
    got = {op_key(item.subject, item.predicate, item.object, item.op) for item in predicted}
    tp = len(want & got)
    return tp, len(got - want), len(want - got)


def evaluate(
    provider: LLMProvider,
    cases: Sequence[GoldCase],
    *,
    skip_fake: bool = False,
) -> Report:
    """Run extract + evidence guard on each case and micro-average the scores."""
    rows: list[CaseScore] = []
    skipped = 0
    for case in cases:
        if skip_fake and case.skip_fake:
            skipped += 1
            continue
        snapshot = ExtractSnapshot(
            reference_time=case.reference_time,
            registry=case.registry or _DEFAULT_REGISTRY,
            facts=case.facts,
        )
        result = extract(provider, snapshot, [{"role": "user", "content": case.text}])
        predicted = keep_ops(result.ops, case.text)
        tp, fp, fn = score_ops(case.expected, predicted)
        rows.append(CaseScore(id=case.id, category=case.category, tp=tp, fp=fp, fn=fn))
    return _report(rows, skipped=skipped)


def default_cases_path() -> Path:
    """``tests/golden/v1.jsonl`` in a source checkout."""
    repo = Path(__file__).resolve().parents[3] / "tests" / "golden" / "v1.jsonl"
    if repo.is_file():
        return repo
    cwd = Path.cwd() / "tests" / "golden" / "v1.jsonl"
    if cwd.is_file():
        return cwd
    msg = "could not find tests/golden/v1.jsonl; pass --path"
    raise FileNotFoundError(msg)


def _report(rows: Sequence[CaseScore], *, skipped: int) -> Report:
    tp = sum(row.tp for row in rows)
    fp = sum(row.fp for row in rows)
    fn = sum(row.fn for row in rows)
    buckets: dict[str, list[CaseScore]] = defaultdict(list)
    for row in rows:
        buckets[row.category].append(row)
    by_category = {
        name: (
            _ratio(sum(item.tp for item in group), sum(item.tp + item.fp for item in group)),
            _ratio(sum(item.tp for item in group), sum(item.tp + item.fn for item in group)),
            len(group),
        )
        for name, group in sorted(buckets.items())
    }
    return Report(
        cases=len(rows),
        skipped=skipped,
        tp=tp,
        fp=fp,
        fn=fn,
        precision=_ratio(tp, tp + fp),
        recall=_ratio(tp, tp + fn),
        by_category=by_category,
    )


def _ratio(num: int, den: int) -> float:
    if den == 0:
        return 1.0
    return num / den
