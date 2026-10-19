"""Deterministic extractor for tests. No network."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from tensemem.core.models import ExtractedOp, ExtractionResult, OpKind
from tensemem.providers.llm.base import ProviderError, last_user_text

T = TypeVar("T", bound=BaseModel)

_CITY = r"([A-Z][\w]+(?:\s+[A-Z][\w]+)*)"
_HEDGE = re.compile(
    r"\b(?:if|might|maybe|would be|thinking about|going to|planning to|"
    r"gonna|hope to|wish i|as if)\b",
    re.IGNORECASE,
)
_THIRD = re.compile(rf"My (\w+) lives in {_CITY}")
_RETRACT_CITY = re.compile(rf"I (?:don't|do not|no longer) live in {_CITY}")
_DENY_CITY = re.compile(rf"I never lived in {_CITY}")
_LIVE = re.compile(rf"(?:I )?(?:moved to|live in) {_CITY}")
_LANG = re.compile(
    r"(?:(?P<mod>no longer|only|also)\s+)?write(?:s)?\s+(?P<lang>[A-Za-z][A-Za-z0-9+#]+)",
    re.IGNORECASE,
)
_DIET = re.compile(r"I(?:'m| am) (vegetarian|vegan|pescatarian|gluten-free)\b", re.IGNORECASE)
_WORK = re.compile(rf"I work (?:at|for) {_CITY}")
_TITLE = re.compile(r"I(?:'m| am) (?:a|an) ([a-z]+(?:\s+[a-z]+)*)", re.IGNORECASE)
_ALLERGY = re.compile(r"I(?:'m| am) allergic to ([a-z]+(?:\s+[a-z]+)*)", re.IGNORECASE)
_PREFER = re.compile(r"I prefer ([A-Za-z][\w+#]*)")
_NAME = re.compile(rf"My name is {_CITY}")
_ZONE = re.compile(r"My timezone is ([A-Za-z][\w/+-]+)")
_PET = re.compile(r"I have a (dog|cat|bird)\b", re.IGNORECASE)
_TOOL = re.compile(r"I use ([A-Z][\w+#]+(?:\s+[A-Z][\w+#]+)*)")


class FakeExtractor:
    """Scripted or rule-based ``LLMProvider`` used by CI."""

    model = "fake"
    cache_namespace = "fake"

    def __init__(
        self,
        responses: Sequence[BaseModel] | Mapping[str, BaseModel] | None = None,
    ) -> None:
        self.calls: list[list[dict[str, str]]] = []
        if isinstance(responses, Mapping):
            self._by_text = dict(responses)
            self._queue: list[BaseModel] = []
        elif responses is None:
            self._by_text = {}
            self._queue = []
        else:
            self._by_text = {}
            self._queue = list(responses)

    def structured(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        **kwargs: Any,
    ) -> T:
        del kwargs
        recorded = [dict(message) for message in messages]
        self.calls.append(recorded)
        text = last_user_text(recorded)
        if text in self._by_text:
            return _as_schema(self._by_text[text], schema)
        if self._queue:
            return _as_schema(self._queue.pop(0), schema)
        return _as_schema(_rule_extract(text), schema)


def _as_schema(value: BaseModel, schema: type[T]) -> T:
    try:
        return schema.model_validate(value.model_dump())
    except Exception as exc:
        msg = f"FakeExtractor cannot fill {schema.__name__}"
        raise ProviderError(msg) from exc


def _rule_extract(text: str) -> ExtractionResult:
    ops: list[ExtractedOp] = []
    ops.extend(_third_party_cities(text))
    ops.extend(_retract_cities(text))
    ops.extend(_deny_cities(text))
    taken = {op.object.casefold() for op in ops if op.predicate == "lives_in"}
    ops.extend(_live_cities(text, occupied=taken))
    ops.extend(_languages(text))
    ops.extend(_simple(text, _DIET, "diet", OpKind.SET))
    ops.extend(_simple(text, _WORK, "works_at", OpKind.SET))
    ops.extend(_titles(text))
    ops.extend(_simple(text, _ALLERGY, "allergic_to", OpKind.ADD))
    ops.extend(_simple(text, _PREFER, "prefers", OpKind.ADD))
    ops.extend(_simple(text, _NAME, "name", OpKind.SET))
    ops.extend(_simple(text, _ZONE, "timezone", OpKind.SET))
    ops.extend(_simple(text, _PET, "pet", OpKind.ADD))
    ops.extend(_simple(text, _TOOL, "uses_tool", OpKind.ADD))
    return ExtractionResult(ops=tuple(ops))


def _op(
    predicate: str,
    obj: str,
    evidence: str,
    *,
    subject: str = "user",
    op: OpKind = OpKind.SET,
) -> ExtractedOp:
    return ExtractedOp(
        subject=subject,
        predicate=predicate,
        object=obj,
        op=op,
        evidence=evidence,
    )


def _hedged_before(text: str, start: int) -> bool:
    return _HEDGE.search(text[:start]) is not None


def _third_party_cities(text: str) -> list[ExtractedOp]:
    ops: list[ExtractedOp] = []
    for match in _THIRD.finditer(text):
        if _hedged_before(text, match.start()):
            continue
        relation = match.group(1).casefold()
        ops.append(
            _op(
                "lives_in",
                match.group(2),
                match.group(0),
                subject=f"user.{relation}",
            )
        )
    return ops


def _retract_cities(text: str) -> list[ExtractedOp]:
    return [
        _op("lives_in", match.group(1), match.group(0), op=OpKind.RETRACT)
        for match in _RETRACT_CITY.finditer(text)
        if not _hedged_before(text, match.start())
    ]


def _deny_cities(text: str) -> list[ExtractedOp]:
    return [
        _op("lives_in", match.group(1), match.group(0), op=OpKind.DENY)
        for match in _DENY_CITY.finditer(text)
        if not _hedged_before(text, match.start())
    ]


def _live_cities(text: str, occupied: set[str]) -> list[ExtractedOp]:
    ops: list[ExtractedOp] = []
    for match in _LIVE.finditer(text):
        city = match.group(1)
        if city.casefold() in occupied or _hedged_before(text, match.start()):
            continue
        prefix = text[: match.start()].rstrip().casefold()
        if prefix.endswith(("don't", "do not", "no longer", "never", "not")):
            continue
        ops.append(_op("lives_in", city, match.group(0)))
    return ops


def _languages(text: str) -> list[ExtractedOp]:
    ops: list[ExtractedOp] = []
    for match in _LANG.finditer(text):
        if _hedged_before(text, match.start()):
            continue
        modifier = (match.group("mod") or "").casefold()
        if modifier == "no longer":
            kind = OpKind.REMOVE
        elif modifier == "only":
            kind = OpKind.REPLACE_SET
        else:
            kind = OpKind.ADD
        ops.append(_op("uses_language", match.group("lang"), match.group(0), op=kind))
    return ops


def _titles(text: str) -> list[ExtractedOp]:
    ops: list[ExtractedOp] = []
    for match in _TITLE.finditer(text):
        if _hedged_before(text, match.start()):
            continue
        title = match.group(1)
        if title.casefold() in {"vegetarian", "vegan", "pescatarian", "gluten-free"}:
            continue
        if "allergic" in title.casefold():
            continue
        ops.append(_op("job_title", title, match.group(0)))
    return ops


def _simple(text: str, pattern: re.Pattern[str], predicate: str, op: OpKind) -> list[ExtractedOp]:
    return [
        _op(predicate, match.group(1), match.group(0), op=op)
        for match in pattern.finditer(text)
        if not _hedged_before(text, match.start())
    ]
