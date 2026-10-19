"""Domain types shared by the resolver, storage, and public API.

These are pure data models. Persistence and the decision table live in later
modules; this file is the contract they share.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Cardinality(StrEnum):
    ONE = "ONE"
    MANY = "MANY"


class OpKind(StrEnum):
    SET = "SET"
    ADD = "ADD"
    REMOVE = "REMOVE"
    RETRACT = "RETRACT"
    REPLACE_SET = "REPLACE_SET"
    DENY = "DENY"


class Modality(StrEnum):
    ASSERTED = "asserted"
    PLANNED = "planned"
    HYPOTHETICAL = "hypothetical"
    NEGATED = "negated"


class ValidPrecision(StrEnum):
    INSTANT = "instant"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


class FactStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"
    STALE = "STALE"
    REJECTED = "REJECTED"
    DELETED = "DELETED"


class FactSource(StrEnum):
    EXTRACTED = "extracted"
    EXPLICIT = "explicit"
    DERIVED = "derived"
    IMPORTED = "imported"


class EdgeKind(StrEnum):
    SUPERSEDES = "SUPERSEDES"
    EVIDENCED_BY = "EVIDENCED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    CONTRADICTS = "CONTRADICTS"


class EpisodeKind(StrEnum):
    MESSAGE = "message"
    EXPLICIT_OP = "explicit_op"


class EpisodeRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class EpisodeStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    DISMISSED = "DISMISSED"
    DELETED = "DELETED"


class JobKind(StrEnum):
    EXTRACT = "extract"
    EMBED = "embed"
    DERIVE = "derive"
    REBUILD = "rebuild"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    DONE = "DONE"
    DEAD = "DEAD"


ValueType = Literal["text", "entity", "number", "date", "bool"]
EntityKind = Literal["person", "place", "org", "tech", "thing", "self"]


class PredicateSpec(BaseModel):
    """Definition of a predicate: from the starter ontology, a developer, or the extractor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    cardinality: Cardinality = Cardinality.ONE
    description: str = ""
    value_type: ValueType = "text"
    pinned: bool = False
    aliases: tuple[str, ...] = ()


class Predicate(BaseModel):
    """A predicate stored in the registry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    name: str
    cardinality: Cardinality
    description: str
    value_type: ValueType
    pinned: bool
    builtin: bool


class ScopeKey(BaseModel):
    """Identifies whose memory this is."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(min_length=1)
    agent_id: str = ""
    namespace: str = Field(default="default", min_length=1)


class Scope(BaseModel):
    """A stored scope plus the entity that represents its user ("self")."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    key: ScopeKey
    self_entity_id: int
    applied_seq: int = Field(ge=0)
    projection_version: int = Field(ge=1)


class ExtractedOp(BaseModel):
    """One typed operation proposed by the extractor (or built by the deterministic API)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str
    predicate: str
    object: str
    op: OpKind
    modality: Modality = Modality.ASSERTED
    valid_from: str | None = None
    valid_precision: ValidPrecision = ValidPrecision.UNKNOWN
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    new_predicate: PredicateSpec | None = None
    evidence: str = ""
    is_confirmation: bool = Field(
        default=False,
        description="True when the user only confirmed an existing fact, not a new claim.",
    )


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ops: tuple[ExtractedOp, ...] = ()


class Freshness(BaseModel):
    """How up to date a read is relative to the episode log (ADR 0006)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of_seq: int = Field(ge=0)
    latest_seq: int = Field(ge=0)
    pending: int = Field(ge=0)
    failed: int = Field(ge=0)
    projection_version: int = Field(ge=1, default=1)

    @property
    def is_current(self) -> bool:
        return self.pending == 0 and self.failed == 0


class AddResult(BaseModel):
    """Returned by ``Memory.add`` so callers can wait for read-your-writes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    seq: int = Field(ge=1)
    episode_ids: tuple[str, ...] = ()
    job_id: str | None = None


class JobView(BaseModel):
    """One outbox row, as returned by ``Memory.jobs``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: JobKind
    scope_id: int
    status: JobStatus
    attempts: int = Field(ge=0)
    next_run_at: str
    lease_until: str | None = None
    last_error: str | None = None
    episode_id: int | None = None
    owner_kind: str | None = None
    owner_id: int | None = None
    embed_text: str | None = None


class FactView(BaseModel):
    """Public shape of a fact as returned by ``state`` / ``history`` / ``explain``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    subject: str
    predicate: str
    object: str
    status: FactStatus
    modality: Modality = Modality.ASSERTED
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    valid_from: str | None = None
    valid_to: str | None = None
    valid_precision: ValidPrecision = ValidPrecision.UNKNOWN
    recorded_at: str
    recorded_seq: int = Field(ge=0)
    cardinality: Cardinality = Cardinality.ONE
    pinned: bool = False


class FactEventView(BaseModel):
    """One row from ``fact_events``, as returned by ``explain``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    from_status: FactStatus | None = None
    to_status: FactStatus
    reason: str
    episode_id: int | None = None
    at: str


class FactSet(BaseModel):
    """Facts plus the freshness of the snapshot they came from (ADR 0006)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    facts: tuple[FactView, ...] = ()
    freshness: Freshness

    @property
    def values(self) -> dict[str, str | tuple[str, ...]]:
        """Current (ACTIVE) values for the self subject. MANY predicates return a tuple."""
        return _values_for(
            fact
            for fact in self.facts
            if fact.status is FactStatus.ACTIVE and fact.subject == "user"
        )

    @property
    def by_subject(self) -> dict[str, dict[str, str | tuple[str, ...]]]:
        """Current (ACTIVE) values keyed by subject, then predicate."""
        subjects: dict[str, list[FactView]] = {}
        for fact in self.facts:
            if fact.status is FactStatus.ACTIVE:
                subjects.setdefault(fact.subject, []).append(fact)
        return {name: _values_for(group) for name, group in subjects.items()}


def _values_for(facts: Iterable[FactView]) -> dict[str, str | tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    kinds: dict[str, Cardinality] = {}
    for fact in facts:
        grouped.setdefault(fact.predicate, []).append(fact.object)
        kinds[fact.predicate] = fact.cardinality
    out: dict[str, str | tuple[str, ...]] = {}
    for name, objects in grouped.items():
        if kinds[name] is Cardinality.MANY:
            out[name] = tuple(sorted(objects, key=str.casefold))
        else:
            out[name] = objects[0]
    return out


class ExplainResult(BaseModel):
    """Provenance for one fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact: FactView
    events: tuple[FactEventView, ...] = ()
    evidence_episode_ids: tuple[int, ...] = ()
    superseded_by: str | None = None


class ContextFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"
    XML = "xml"


class ContextDebugItem(BaseModel):
    """Why one packed item was included (design §11.4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: Literal["fact", "episode", "hot"]
    score: float = 0.0
    relevance: float = 0.0
    recency: float = 0.0
    reason: str = ""


class SearchHit(BaseModel):
    """One ranked fact or episode from ``Memory.search``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["fact", "episode"]
    id: str
    text: str
    score: float = Field(ge=0.0)
    status: FactStatus | None = None
    predicate: str | None = None


class SearchResult(BaseModel):
    """Ranked facts and episodes plus the freshness of that snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    hits: tuple[SearchHit, ...] = ()
    freshness: Freshness
    debug: tuple[ContextDebugItem, ...] = ()


class ContextResult(BaseModel):
    """Rendered prompt block from ``Memory.context``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    facts_used: tuple[str, ...] = ()
    token_count: int = Field(ge=0)
    freshness: Freshness
    debug: tuple[ContextDebugItem, ...] = ()


class MemoryStats(BaseModel):
    """Counts from ``Memory.stats()`` for queue depth, facts, and rough size."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scopes: int = Field(ge=0)
    episodes: int = Field(ge=0)
    facts: int = Field(ge=0)
    facts_by_status: dict[str, int] = Field(default_factory=dict)
    jobs_by_status: dict[str, int] = Field(default_factory=dict)
    queue_depth: int = Field(ge=0)
    pending_episodes: int = Field(ge=0)
    failed_episodes: int = Field(ge=0)
    rejected_claims: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    corrections_by_extractor: dict[str, int] = Field(default_factory=dict)
    projection_version: int = Field(ge=1, default=1)


class OnStale(StrEnum):
    FLAG = "flag"
    RAISE = "raise"


class StaleMemoryError(Exception):
    """Raised when ``on_stale='raise'`` and the watermark has not reached ``min_seq``."""

    def __init__(self, *, min_seq: int, freshness: Freshness) -> None:
        self.min_seq = min_seq
        self.freshness = freshness
        super().__init__(
            f"memory not current: need seq>={min_seq}, as_of_seq={freshness.as_of_seq}, "
            f"pending={freshness.pending}, failed={freshness.failed}"
        )


# Resolved mutation intents produced by the decision table (Day 7-8). Kept here
# so storage and the resolver share one vocabulary from day one.
MutationKind = Literal[
    "insert_active",
    "insert_candidate",
    "insert_historical",
    "reinforce",
    "supersede",
    "retract",
    "reject",
    "drop",
]


class Mutation(BaseModel):
    """One state change decided by ``resolve()`` before ``apply()`` writes it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MutationKind
    op: ExtractedOp
    reason: str
    target_fact_id: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason_nonempty(cls, value: str) -> str:
        if not value.strip():
            msg = "mutation reason must be non-empty"
            raise ValueError(msg)
        return value
