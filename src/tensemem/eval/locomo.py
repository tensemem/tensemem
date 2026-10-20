"""Load a LoCoMo-shaped JSON pack and score recalled context (ADR 0013)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import cast

import dateparser
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from tensemem.core.clock import FrozenClock, format_instant
from tensemem.core.models import ExtractedOp, ExtractionResult, PredicateSpec, ValidPrecision
from tensemem.core.ontology import EntitySpec, Ontology
from tensemem.core.temporal import resolve_valid_time
from tensemem.eval.longmem import TypeScore
from tensemem.eval.tensebench import BenchPredicate, ScriptedOp
from tensemem.memory import Memory
from tensemem.providers.llm.fake import FakeExtractor

# Official evaluation.py IDs — not the paper's numbered list.
_CATEGORY = {
    1: "multi-hop",
    2: "temporal",
    3: "open-domain",
    4: "single-hop",
    5: "adversarial",
}
_NAMES = tuple(_CATEGORY[index] for index in range(1, 6))
_PACKAGED = "locomo_pilot.json"
_REF = "2026-10-18T11:00:00.000000Z"
_SESSION = re.compile(r"^session_(\d+)$")


class LocomoTurn(BaseModel):
    """One dialog turn. ``ops`` is a CI extension; official files omit it."""

    model_config = ConfigDict(extra="ignore")

    speaker: str = ""
    text: str = ""
    dia_id: str = ""
    blip_caption: str | None = None
    ops: tuple[ScriptedOp, ...] | None = None

    def content(self) -> str:
        """Spoken text, or the image caption when the turn is photo-only."""
        spoken = self.text.strip()
        if spoken:
            return spoken
        return (self.blip_caption or "").strip()


class LocomoQA(BaseModel):
    """One official QA row, plus an optional abstention trap for category 5."""

    model_config = ConfigDict(extra="ignore")

    question: str
    answer: str = ""
    category: int
    evidence: tuple[str, ...] = ()
    abstain_trap: str | None = None

    @field_validator("answer", mode="before")
    @classmethod
    def _stringify_answer(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)

    @computed_field
    @property
    def category_name(self) -> str:
        return _CATEGORY.get(self.category, f"category-{self.category}")


class LocomoConversation(BaseModel):
    """Speaker names plus dynamic ``session_N`` / ``session_N_date_time`` keys."""

    model_config = ConfigDict(extra="allow")

    speaker_a: str = ""
    speaker_b: str = ""


class LocomoSample(BaseModel):
    """One official conversation plus optional predicate seeds."""

    model_config = ConfigDict(extra="ignore")

    sample_id: str
    conversation: LocomoConversation
    qa: tuple[LocomoQA, ...]
    predicates: tuple[BenchPredicate, ...] = ()


class LocomoReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversations: int = Field(ge=0)
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


def load_samples(path: Path | None = None) -> tuple[LocomoSample, ...]:
    """Read a JSON array or JSONL file. Default is the packaged pilot pack."""
    text = path.read_text(encoding="utf-8") if path is not None else _packaged_text()
    stripped = text.lstrip()
    if stripped.startswith("["):
        parsed: object = json.loads(stripped)
        if not isinstance(parsed, list):
            raise ValueError("LoCoMo pack must be a JSON array or JSONL")
        return tuple(LocomoSample.model_validate(row) for row in cast(list[object], parsed))
    samples = [LocomoSample.model_validate_json(line) for line in text.splitlines() if line.strip()]
    return tuple(samples)


def default_samples_path() -> Path:
    """Filesystem path to the packaged pack when it is not inside a zip."""
    resource = files("tensemem.eval").joinpath(_PACKAGED)
    if isinstance(resource, Path) and resource.is_file():
        return resource
    msg = "packaged LoCoMo pilot is not on the filesystem; pass --path"
    raise FileNotFoundError(msg)


def run_locomo(path: Path | None = None) -> LocomoReport:
    """Replay both speakers and score ``context()`` against each gold answer."""
    samples = load_samples(path)
    acc = _Acc(conversations=len(samples))
    for sample in samples:
        _score(sample, acc)
    return acc.freeze()


def format_report(report: LocomoReport) -> str:
    lines = [f"LoCoMo adapter  conversations: {report.conversations}  scored: {report.cases}"]
    lines.append(f"  accuracy: {_fmt(report.accuracy, report.ok, report.cases)}")
    for name in _NAMES:
        score = report.by_type.get(name)
        if score is None:
            lines.append(f"  {name}: n/a")
            continue
        lines.append(f"  {name}: {_fmt(score.accuracy, score.ok, score.n)}")
    tokens = report.tokens_per_answer
    token_text = "n/a" if tokens is None else f"{tokens:.1f}"
    lines.append(f"  tokens_per_answer: {token_text}")
    return "\n".join(lines)


def session_stamp(raw: str) -> str | None:
    """Parse a LoCoMo session stamp, or an ISO / LongMemEval date with known precision."""
    text = raw.strip()
    if not text:
        return None
    parsed = dateparser.parse(
        text,
        languages=["en"],
        settings={
            "TIMEZONE": "UTC",
            "TO_TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DAY_OF_MONTH": "first",
        },
    )
    if parsed is not None and _looks_dated(text, parsed):
        return format_instant(parsed.astimezone(UTC))
    try:
        resolved = resolve_valid_time(text, reference_time=_REF)
    except (ValueError, TypeError):
        return None
    if resolved.valid_precision is ValidPrecision.UNKNOWN:
        return None
    return resolved.valid_from


def _score(sample: LocomoSample, acc: _Acc) -> None:
    sessions = _iter_sessions(sample.conversation)
    scripts = _scripts(sessions)
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(
        ":memory:",
        clock=clock,
        llm=FakeExtractor(scripts),
        start_worker=False,
    ) as mem:
        mem.seed(_ontology(sample, sessions))
        for _index, stamp, turns in sessions:
            occurred = session_stamp(stamp)
            for turn in turns:
                content = turn.content()
                if not content:
                    continue
                clock.advance(seconds=1)
                mem.add(sample.sample_id, content, wait=True, occurred_at=occurred)
        for qa in sample.qa:
            ctx = mem.context(
                sample.sample_id,
                qa.question,
                include_history=qa.category == 2,
            )
            acc.token_sum += ctx.token_count
            acc.token_n += 1
            hit = _hit(qa, ctx.text)
            if hit is None:
                continue
            acc.bump(qa.category_name, hit)


def _hit(qa: LocomoQA, text: str) -> bool | None:
    """``None`` means the item is not scored (official adversarial prose)."""
    if qa.category == 5:
        trap = (qa.abstain_trap or "").strip()
        if not trap:
            return None
        return not _mentions(_current_section(text), trap)
    answer = qa.answer.strip()
    if qa.category == 3 and ";" in answer:
        answer = answer.split(";", 1)[0].strip()
    if not answer:
        return False
    if qa.category == 1:
        parts = [part.strip() for part in answer.split(",") if part.strip()]
        return all(_mentions(text, part) for part in parts)
    return _mentions(text, answer)


def _iter_sessions(
    conversation: LocomoConversation,
) -> list[tuple[int, str, tuple[LocomoTurn, ...]]]:
    extra = conversation.model_extra or {}
    rows: list[tuple[int, str, tuple[LocomoTurn, ...]]] = []
    for key, value in extra.items():
        match = _SESSION.fullmatch(key)
        if match is None or not isinstance(value, list):
            continue
        index = int(match.group(1))
        turns = tuple(LocomoTurn.model_validate(item) for item in cast(list[object], value))
        raw = extra.get(f"session_{index}_date_time", "")
        stamp = raw if isinstance(raw, str) else ""
        rows.append((index, stamp, turns))
    rows.sort(key=lambda row: row[0])
    return rows


def _scripts(
    sessions: list[tuple[int, str, tuple[LocomoTurn, ...]]],
) -> dict[str, ExtractionResult]:
    mapped: dict[str, ExtractionResult] = {}
    for _index, _stamp, turns in sessions:
        for turn in turns:
            if turn.ops is None:
                continue
            content = turn.content()
            if not content:
                continue
            mapped[content] = ExtractionResult(ops=_ops(turn))
    return mapped


def _ops(turn: LocomoTurn) -> tuple[ExtractedOp, ...]:
    if turn.ops is None:
        return ()
    return tuple(
        ExtractedOp(
            subject=_subject(item, turn),
            predicate=item.predicate,
            object=item.object,
            op=item.op,
            evidence=item.evidence or turn.content(),
            valid_from=item.valid_from,
        )
        for item in turn.ops
    )


def _subject(item: ScriptedOp, turn: LocomoTurn) -> str:
    if item.subject != "user":
        return item.subject
    speaker = turn.speaker.strip()
    return speaker or item.subject


def _ontology(
    sample: LocomoSample,
    sessions: list[tuple[int, str, tuple[LocomoTurn, ...]]],
) -> Ontology:
    specs = {
        pred.name: PredicateSpec(name=pred.name, cardinality=pred.cardinality, aliases=pred.aliases)
        for pred in sample.predicates
    }
    for _index, _stamp, turns in sessions:
        for turn in turns:
            if turn.ops is None:
                continue
            for op in turn.ops:
                specs.setdefault(op.predicate, PredicateSpec(name=op.predicate))
    entities = [
        EntitySpec(name=name, kind="person")
        for name in (sample.conversation.speaker_a, sample.conversation.speaker_b)
        if name.strip()
    ]
    return Ontology(predicates=tuple(specs.values()), entities=tuple(entities))


def _looks_dated(text: str, parsed: datetime) -> bool:
    """Reject dateparser guesses that did not see a calendar year in the stamp."""
    del parsed
    return bool(re.search(r"\d{4}", text))


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
    conversations: int = 0
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

    def freeze(self) -> LocomoReport:
        by_type = {name: TypeScore(name=name, ok=0, n=0) for name in _NAMES}
        scored = 0
        for name, (ok, n) in self.types.items():
            by_type[name] = TypeScore(name=name, ok=ok, n=n)
            scored += n
        return LocomoReport(
            conversations=self.conversations,
            cases=scored,
            ok=self.ok,
            token_sum=self.token_sum,
            token_n=self.token_n,
            by_type=by_type,
        )
