"""Load a LongMemEval-shaped JSON pack and score recalled context (ADR 0012)."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, computed_field

from tensemem.core.clock import FrozenClock, format_instant
from tensemem.core.models import ExtractedOp, ExtractionResult, PredicateSpec, ValidPrecision
from tensemem.core.ontology import Ontology
from tensemem.core.temporal import resolve_valid_time
from tensemem.eval.tensebench import BenchPredicate, ScriptedOp
from tensemem.memory import Memory
from tensemem.providers.llm.base import LLMProvider
from tensemem.providers.llm.fake import FakeExtractor

QuestionType = Literal[
    "single-session-user",
    "single-session-assistant",
    "single-session-preference",
    "temporal-reasoning",
    "knowledge-update",
    "multi-session",
]

_TYPES: tuple[str, ...] = (
    "single-session-user",
    "single-session-assistant",
    "single-session-preference",
    "temporal-reasoning",
    "knowledge-update",
    "multi-session",
)
_PACKAGED = "longmem_pilot.json"
_REF = "2026-10-18T11:00:00.000000Z"
_LME_DATE = re.compile(
    r"^(\d{4})/(\d{2})/(\d{2})"
    r"(?:\s+\([A-Za-z]{3}\))?"
    r"(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?$"
)


class LmeTurn(BaseModel):
    """One haystack turn. ``ops`` is a CI extension; official files omit it."""

    model_config = ConfigDict(extra="ignore")

    role: str
    content: str
    has_answer: bool = False
    ops: tuple[ScriptedOp, ...] | None = None


class LmeItem(BaseModel):
    """One official LongMemEval instance, plus optional predicate seeds."""

    model_config = ConfigDict(extra="ignore")

    question_id: str
    question_type: str
    question: str
    answer: str = ""
    abstain_trap: str | None = None
    question_date: str = ""
    haystack_session_ids: tuple[str, ...] = ()
    haystack_dates: tuple[str, ...] = ()
    haystack_sessions: tuple[tuple[LmeTurn, ...], ...]
    answer_session_ids: tuple[str, ...] = ()
    predicates: tuple[BenchPredicate, ...] = ()

    @computed_field
    @property
    def abstention(self) -> bool:
        return self.question_id.endswith("_abs")


class TypeScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    ok: int = Field(ge=0)
    n: int = Field(ge=0)

    @computed_field
    @property
    def accuracy(self) -> float | None:
        if self.n == 0:
            return None
        return self.ok / self.n


class LongMemReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cases: int = Field(ge=0)
    ok: int = Field(ge=0)
    token_sum: int = Field(ge=0)
    token_n: int = Field(ge=0)
    by_type: dict[str, TypeScore]

    @computed_field
    @property
    def accuracy(self) -> float | None:
        if self.cases == 0:
            return None
        return self.ok / self.cases

    @computed_field
    @property
    def tokens_per_answer(self) -> float | None:
        if self.token_n == 0:
            return None
        return self.token_sum / self.token_n


def load_items(path: Path | None = None) -> tuple[LmeItem, ...]:
    """Read a JSON array or JSONL file. Default is the packaged pilot pack."""
    text = path.read_text(encoding="utf-8") if path is not None else _packaged_text()
    stripped = text.lstrip()
    if stripped.startswith("["):
        parsed: object = json.loads(stripped)
        if not isinstance(parsed, list):
            raise ValueError("LongMemEval pack must be a JSON array or JSONL")
        loaded: list[LmeItem] = []
        for row in cast(list[object], parsed):
            loaded.append(LmeItem.model_validate(row))
        return tuple(loaded)
    items = [LmeItem.model_validate_json(line) for line in text.splitlines() if line.strip()]
    return tuple(items)


def default_items_path() -> Path:
    """Filesystem path to the packaged pack when it is not inside a zip."""
    resource = files("tensemem.eval").joinpath(_PACKAGED)
    if isinstance(resource, Path) and resource.is_file():
        return resource
    msg = "packaged LongMemEval pilot is not on the filesystem; pass --path"
    raise FileNotFoundError(msg)


def run_longmem(path: Path | None = None, *, llm: LLMProvider | None = None) -> LongMemReport:
    """Replay user turns and score ``context()`` against each gold answer."""
    items = load_items(path)
    acc = _Acc()
    for item in items:
        _score(item, acc, llm=llm)
    return acc.freeze()


def format_report(report: LongMemReport) -> str:
    lines = [f"LongMemEval adapter  scored: {report.cases}"]
    lines.append(f"  accuracy: {_fmt(report.accuracy, report.ok, report.cases)}")
    for name in (*_TYPES, "abstention"):
        score = report.by_type.get(name)
        if score is None:
            lines.append(f"  {name}: n/a")
            continue
        lines.append(f"  {name}: {_fmt(score.accuracy, score.ok, score.n)}")
    tokens = report.tokens_per_answer
    token_text = "n/a" if tokens is None else f"{tokens:.1f}"
    lines.append(f"  tokens_per_answer: {token_text}")
    return "\n".join(lines)


def _score(item: LmeItem, acc: _Acc, *, llm: LLMProvider | None = None) -> None:
    scripts = _scripts(item)
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(
        ":memory:",
        clock=clock,
        llm=llm if llm is not None else FakeExtractor(scripts),
        start_worker=False,
    ) as mem:
        mem.seed(_ontology(item))
        for index, session in enumerate(item.haystack_sessions):
            occurred = session_stamp(_date_at(item.haystack_dates, index))
            for turn in session:
                if turn.role != "user" or not turn.content.strip():
                    continue
                clock.advance(seconds=1)
                mem.add(item.question_id, turn.content, wait=True, occurred_at=occurred)
        ctx = mem.context(
            item.question_id,
            item.question,
            include_history=item.question_type == "temporal-reasoning",
        )
    acc.token_sum += ctx.token_count
    acc.token_n += 1
    hit = _hit(item, ctx.text)
    if hit is None:
        return
    bucket = "abstention" if item.abstention else item.question_type
    acc.bump(bucket, hit)


def _hit(item: LmeItem, text: str) -> bool | None:
    """``None`` means the item is not scored (official abstention prose)."""
    if item.abstention:
        trap = (item.abstain_trap or "").strip()
        if not trap:
            return None
        return not _mentions(_current_section(text), trap)
    if not item.answer.strip():
        return False
    return _mentions(text, item.answer)


def _scripts(item: LmeItem) -> dict[str, ExtractionResult]:
    mapped: dict[str, ExtractionResult] = {}
    for session in item.haystack_sessions:
        for turn in session:
            if turn.ops is None:
                continue
            mapped[turn.content] = ExtractionResult(ops=_ops(turn))
    return mapped


def _ops(turn: LmeTurn) -> tuple[ExtractedOp, ...]:
    if turn.ops is None:
        return ()
    return tuple(
        ExtractedOp(
            subject=item.subject,
            predicate=item.predicate,
            object=item.object,
            op=item.op,
            evidence=item.evidence or turn.content,
            valid_from=item.valid_from,
        )
        for item in turn.ops
    )


def _ontology(item: LmeItem) -> Ontology:
    specs = {
        pred.name: PredicateSpec(name=pred.name, cardinality=pred.cardinality, aliases=pred.aliases)
        for pred in item.predicates
    }
    for session in item.haystack_sessions:
        for turn in session:
            if turn.ops is None:
                continue
            for op in turn.ops:
                specs.setdefault(op.predicate, PredicateSpec(name=op.predicate))
    return Ontology(predicates=tuple(specs.values()))


def _date_at(dates: Sequence[str], index: int) -> str:
    if index < len(dates):
        return dates[index]
    return ""


def session_stamp(raw: str) -> str | None:
    """Parse a LongMemEval session stamp, or an ISO date with known precision."""
    text = raw.strip()
    if not text:
        return None
    parsed = _parse_lme_stamp(text)
    if parsed is not None:
        return format_instant(parsed)
    try:
        resolved = resolve_valid_time(text, reference_time=_REF)
    except (ValueError, TypeError):
        return None
    if resolved.valid_precision is ValidPrecision.UNKNOWN:
        return None
    return resolved.valid_from


def _parse_lme_stamp(text: str) -> datetime | None:
    """``YYYY/MM/DD [(Mon)] [HH:MM[:SS]]`` as used in published haystack dates."""
    match = _LME_DATE.match(text)
    if match is None:
        return None
    year, month, day, hour, minute, second = match.groups()
    try:
        return datetime(
            int(year),
            int(month),
            int(day),
            int(hour or 0),
            int(minute or 0),
            int(second or 0),
            tzinfo=UTC,
        )
    except ValueError:
        return None


def _packaged_text() -> str:
    return files("tensemem.eval").joinpath(_PACKAGED).read_text(encoding="utf-8")


def _empty_counts() -> dict[str, list[int]]:
    return {}


def _mentions(text: str, value: str) -> bool:
    pattern = re.compile(rf"(?<!\w){re.escape(value)}(?!\w)", re.IGNORECASE)
    return pattern.search(text) is not None


def _current_section(text: str) -> str:
    cut = text
    for marker in ("## Possibly relevant", "## Said recently"):
        if marker in cut:
            cut = cut.split(marker, 1)[0]
    return cut


def _fmt(value: float | None, num: int, den: int) -> str:
    if value is None or den == 0:
        return "n/a"
    return f"{value:.3f}  ({num}/{den})"


@dataclass
class _Acc:
    ok: int = 0
    token_sum: int = 0
    token_n: int = 0
    types: dict[str, list[int]] = field(default_factory=_empty_counts)

    def bump(self, name: str, hit: bool) -> None:
        bucket = self.types.setdefault(name, [0, 0])
        bucket[1] += 1
        if hit:
            self.ok += 1
            bucket[0] += 1

    def freeze(self) -> LongMemReport:
        by_type = {name: TypeScore(name=name, ok=0, n=0) for name in (*_TYPES, "abstention")}
        scored = 0
        for name, (ok, n) in self.types.items():
            by_type[name] = TypeScore(name=name, ok=ok, n=n)
            scored += n
        return LongMemReport(
            cases=scored,
            ok=self.ok,
            token_sum=self.token_sum,
            token_n=self.token_n,
            by_type=by_type,
        )
