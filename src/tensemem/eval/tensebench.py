"""TenseBench pilot: score whether memory is safe to act on (design §17.4)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from tensemem.core.clock import FrozenClock
from tensemem.core.context import count_tokens
from tensemem.core.models import (
    Cardinality,
    ExtractedOp,
    ExtractionResult,
    FactSet,
    FactStatus,
    OpKind,
    PredicateSpec,
)
from tensemem.core.normalize import normalize_value
from tensemem.core.ontology import EntitySpec, Ontology
from tensemem.memory import Memory
from tensemem.providers.llm.fake import FakeExtractor

SystemName = Literal["tensemem", "concat", "similarity"]

_SYSTEMS: tuple[SystemName, ...] = ("tensemem", "concat", "similarity")
_WORD = re.compile(r"[A-Za-z0-9+#]+")
_PRESENT = re.compile(r"\(previously [^)]*\)", re.IGNORECASE)


class ScriptedOp(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = "user"
    predicate: str
    object: str
    op: OpKind = OpKind.SET
    evidence: str = ""


class BenchTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    ops: tuple[ScriptedOp, ...] | None = None


class BenchPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    cardinality: Cardinality = Cardinality.ONE
    aliases: tuple[str, ...] = ()


class BenchEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: Literal["person", "place", "org", "tech", "thing", "self"] = "thing"
    aliases: tuple[str, ...] = ()


class ExpectFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = "user"
    predicate: str
    object: str


class Scenario(BaseModel):
    """One multi-turn conversation plus the checks to score after it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    category: str
    predicates: tuple[BenchPredicate, ...]
    entities: tuple[BenchEntity, ...] = ()
    turns: tuple[BenchTurn, ...]
    query: str = ""
    expect: tuple[ExpectFact, ...] = ()
    stale: tuple[str, ...] = ()
    history: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    echo: int = Field(default=0, ge=0)
    correct: str | None = None
    rebuild: bool = False
    wait_last: bool = True


class SystemScore(BaseModel):
    """Counts for one system. Rates use 1.0/0.0 when a denominator is 0."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    scenarios: int = Field(ge=0)
    current_ok: int = Field(ge=0)
    current_n: int = Field(ge=0)
    leaks: int = Field(ge=0)
    leak_n: int = Field(ge=0)
    honest: int = Field(ge=0)
    honest_n: int = Field(ge=0)
    contaminated: int = Field(ge=0)
    echo_n: int = Field(ge=0)
    durable: int = Field(ge=0)
    durable_n: int = Field(ge=0)
    history_ok: int = Field(ge=0)
    history_n: int = Field(ge=0)
    token_sum: int = Field(ge=0)
    token_n: int = Field(ge=0)

    @computed_field
    @property
    def current_state_accuracy(self) -> float:
        return _ratio(self.current_ok, self.current_n)

    @computed_field
    @property
    def stale_fact_leak_rate(self) -> float:
        return 0.0 if self.leak_n == 0 else self.leaks / self.leak_n

    @computed_field
    @property
    def freshness_honesty(self) -> float:
        return _ratio(self.honest, self.honest_n)

    @computed_field
    @property
    def contamination_rate(self) -> float:
        return 0.0 if self.echo_n == 0 else self.contaminated / self.echo_n

    @computed_field
    @property
    def correction_durability(self) -> float:
        return _ratio(self.durable, self.durable_n)

    @computed_field
    @property
    def history_accuracy(self) -> float:
        return _ratio(self.history_ok, self.history_n)

    @computed_field
    @property
    def tokens_per_answer(self) -> float:
        return 0.0 if self.token_n == 0 else self.token_sum / self.token_n


class BenchReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cases: int = Field(ge=0)
    systems: dict[str, SystemScore]


def load_scenarios(path: Path) -> tuple[Scenario, ...]:
    rows: list[Scenario] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(Scenario.model_validate_json(line))
    return tuple(rows)


def default_scenarios_path() -> Path:
    """``benchmarks/tensebench/v1.jsonl`` in a source checkout."""
    repo = Path(__file__).resolve().parents[3] / "benchmarks" / "tensebench" / "v1.jsonl"
    if repo.is_file():
        return repo
    cwd = Path.cwd() / "benchmarks" / "tensebench" / "v1.jsonl"
    if cwd.is_file():
        return cwd
    msg = "could not find benchmarks/tensebench/v1.jsonl; pass --path"
    raise FileNotFoundError(msg)


def run_suite(
    path: Path | None = None,
    *,
    systems: Sequence[str] | None = None,
) -> BenchReport:
    """Run every scenario against TenseMem and the published baselines."""
    scenarios = load_scenarios(path or default_scenarios_path())
    wanted = tuple(systems) if systems else _SYSTEMS
    acc = {name: _Acc() for name in wanted}
    for scenario in scenarios:
        texts = tuple(turn.text for turn in scenario.turns)
        if "tensemem" in acc:
            _score_tensemem(scenario, acc["tensemem"])
        if "concat" in acc:
            _score_text(scenario, "\n".join(texts), acc["concat"])
        if "similarity" in acc:
            _score_text(scenario, _similar(texts, scenario.query), acc["similarity"])
    return BenchReport(
        cases=len(scenarios),
        systems={name: bucket.freeze(name) for name, bucket in acc.items()},
    )


def format_report(report: BenchReport) -> str:
    lines = [f"TenseBench v1  scenarios: {report.cases}"]
    for name in _SYSTEMS:
        score = report.systems.get(name)
        if score is None:
            continue
        lines.append(name)
        lines.append(
            f"  current_state_accuracy: {score.current_state_accuracy:.3f}  "
            f"({score.current_ok}/{score.current_n})"
        )
        lines.append(
            f"  stale_fact_leak_rate:   {score.stale_fact_leak_rate:.3f}  "
            f"({score.leaks}/{score.leak_n})"
        )
        lines.append(
            f"  freshness_honesty:      {score.freshness_honesty:.3f}  "
            f"({score.honest}/{score.honest_n})"
        )
        lines.append(
            f"  contamination_rate:     {score.contamination_rate:.3f}  "
            f"({score.contaminated}/{score.echo_n})"
        )
        lines.append(
            f"  correction_durability:  {score.correction_durability:.3f}  "
            f"({score.durable}/{score.durable_n})"
        )
        lines.append(
            f"  history_accuracy:       {score.history_accuracy:.3f}  "
            f"({score.history_ok}/{score.history_n})"
        )
        lines.append(f"  tokens_per_answer:      {score.tokens_per_answer:.1f}")
    return "\n".join(lines)


def _score_tensemem(scenario: Scenario, acc: _Acc) -> None:
    acc.scenarios += 1
    scripts = {
        turn.text: ExtractionResult(ops=_ops_for(turn))
        for turn in scenario.turns
        if turn.ops is not None
    }
    clock = FrozenClock(datetime(2026, 10, 18, 11, 0, 0, tzinfo=UTC))
    with Memory(
        ":memory:",
        clock=clock,
        llm=FakeExtractor(scripts),
        start_worker=False,
    ) as mem:
        mem.seed(_ontology(scenario))
        last = len(scenario.turns) - 1
        for index, turn in enumerate(scenario.turns):
            wait = scenario.wait_last or index != last
            clock.advance(seconds=1)
            mem.add(scenario.id, turn.text, wait=wait)
        if not scenario.wait_last:
            ctx = mem.context(scenario.id, scenario.query)
            acc.honest_n += 1
            if not ctx.freshness.is_current:
                acc.honest += 1
            acc.token_sum += ctx.token_count
            acc.token_n += 1
            return
        if scenario.echo:
            before = _signature(mem.state(scenario.id))
            ctx = mem.context(scenario.id, scenario.query)
            for _ in range(scenario.echo):
                clock.advance(seconds=1)
                mem.add(scenario.id, ctx.text, wait=True)
            acc.echo_n += 1
            if _signature(mem.state(scenario.id)) != before:
                acc.contaminated += 1
        if scenario.correct is not None:
            target = scenario.correct
            wanted = normalize_value(target)
            match = next(
                (
                    fact
                    for fact in mem.state(scenario.id).facts
                    if fact.object == target or normalize_value(fact.object) == wanted
                ),
                None,
            )
            if match is not None:
                mem.correct(match.id)
            if scenario.rebuild:
                mem.rebuild(scenario.id, wait=True)
            acc.durable_n += 1
            if _durable(mem, scenario.id, target):
                acc.durable += 1
        state = mem.state(scenario.id)
        ctx = mem.context(scenario.id, scenario.query)
        acc.token_sum += ctx.token_count
        acc.token_n += 1
        acc.current_n += 1
        if _current_ok(state, scenario.expect):
            acc.current_ok += 1
        if scenario.stale:
            acc.leak_n += 1
            if _leaks(ctx.text, state, scenario.stale):
                acc.leaks += 1
        if scenario.history:
            acc.history_n += 1
            if _history_ok(mem, scenario.id, scenario.history):
                acc.history_ok += 1


def _score_text(scenario: Scenario, answer: str, acc: _Acc) -> None:
    acc.scenarios += 1
    acc.token_sum += count_tokens(answer)
    acc.token_n += 1
    if not scenario.wait_last:
        acc.honest_n += 1
        return
    acc.current_n += 1
    if _text_current(answer, scenario.expect, scenario.stale):
        acc.current_ok += 1
    if scenario.stale:
        acc.leak_n += 1
        if any(_mentions(answer, value) for value in scenario.stale):
            acc.leaks += 1
    if scenario.history:
        acc.history_n += 1
        wanted = [item for values in scenario.history.values() for item in values]
        if wanted and all(_mentions(answer, item) for item in wanted):
            acc.history_ok += 1


def _ontology(scenario: Scenario) -> Ontology:
    predicates = tuple(
        PredicateSpec(name=item.name, cardinality=item.cardinality, aliases=item.aliases)
        for item in scenario.predicates
    )
    entities = tuple(
        EntitySpec(name=item.name, kind=item.kind, aliases=item.aliases)
        for item in scenario.entities
    )
    return Ontology(predicates=predicates, entities=entities)


def _ops_for(turn: BenchTurn) -> tuple[ExtractedOp, ...]:
    if turn.ops is None:
        return ()
    return tuple(
        ExtractedOp(
            subject=item.subject,
            predicate=item.predicate,
            object=item.object,
            op=item.op,
            evidence=item.evidence or turn.text,
        )
        for item in turn.ops
    )


def _active(state: FactSet) -> set[tuple[str, str, str]]:
    return {
        (fact.subject, fact.predicate, normalize_value(fact.object))
        for fact in state.facts
        if fact.status is FactStatus.ACTIVE
    }


def _current_ok(state: FactSet, expect: Sequence[ExpectFact]) -> bool:
    want = {(item.subject, item.predicate, normalize_value(item.object)) for item in expect}
    return _active(state) == want


def _leaks(text: str, state: FactSet, stale: Sequence[str]) -> bool:
    current = _PRESENT.sub("", _current_section(text))
    active = {item[2] for item in _active(state)}
    return any(_mentions(current, value) or normalize_value(value) in active for value in stale)


def _current_section(text: str) -> str:
    """Fact cards only: episode snippets may still quote superseded messages."""
    cut = text
    for marker in ("## Possibly relevant", "## Said recently"):
        if marker in cut:
            cut = cut.split(marker, 1)[0]
    return cut


def _durable(mem: Memory, user_id: str, rejected: str) -> bool:
    key = normalize_value(rejected)
    return all(normalize_value(fact.object) != key for fact in mem.history(user_id).facts)


def _history_ok(mem: Memory, user_id: str, expected: dict[str, tuple[str, ...]]) -> bool:
    for predicate, objects in expected.items():
        got = tuple(
            fact.object for fact in mem.history(user_id, predicate).facts if fact.subject == "user"
        )
        if got != objects:
            return False
    return True


def _signature(state: FactSet) -> tuple[tuple[str, str, str, float, str], ...]:
    return tuple(
        sorted(
            (
                fact.subject,
                fact.predicate,
                normalize_value(fact.object),
                round(fact.confidence, 6),
                fact.id,
            )
            for fact in state.facts
            if fact.status is FactStatus.ACTIVE
        )
    )


def _text_current(answer: str, expect: Sequence[ExpectFact], stale: Sequence[str]) -> bool:
    if any(_mentions(answer, value) for value in stale):
        return False
    return all(_mentions(answer, item.object) for item in expect)


def _similar(turns: Sequence[str], query: str, *, k: int = 2) -> str:
    if not turns:
        return ""
    if not query.strip():
        return "\n".join(turns[-k:])
    ranked = sorted(turns, key=lambda text: _overlap(text, query), reverse=True)
    return "\n".join(ranked[:k])


def _overlap(text: str, query: str) -> int:
    left = set(_WORD.findall(text.casefold()))
    right = set(_WORD.findall(query.casefold()))
    return len(left & right)


def _mentions(text: str, value: str) -> bool:
    pattern = re.compile(rf"(?<!\w){re.escape(value)}(?!\w)", re.IGNORECASE)
    return pattern.search(text) is not None


@dataclass
class _Acc:
    scenarios: int = 0
    current_ok: int = 0
    current_n: int = 0
    leaks: int = 0
    leak_n: int = 0
    honest: int = 0
    honest_n: int = 0
    contaminated: int = 0
    echo_n: int = 0
    durable: int = 0
    durable_n: int = 0
    history_ok: int = 0
    history_n: int = 0
    token_sum: int = 0
    token_n: int = 0

    def freeze(self, name: str) -> SystemScore:
        return SystemScore(
            name=name,
            scenarios=self.scenarios,
            current_ok=self.current_ok,
            current_n=self.current_n,
            leaks=self.leaks,
            leak_n=self.leak_n,
            honest=self.honest,
            honest_n=self.honest_n,
            contaminated=self.contaminated,
            echo_n=self.echo_n,
            durable=self.durable,
            durable_n=self.durable_n,
            history_ok=self.history_ok,
            history_n=self.history_n,
            token_sum=self.token_sum,
            token_n=self.token_n,
        )


def _ratio(num: int, den: int) -> float:
    if den == 0:
        return 1.0
    return num / den
