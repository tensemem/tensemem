"""Deterministic extractor for tests. No network."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel

from tensemem.core.models import ExtractedOp, ExtractionResult, OpKind
from tensemem.providers.llm.base import ProviderError, last_user_text

T = TypeVar("T", bound=BaseModel)

_CITY = re.compile(
    r"(?:moved to|live(?:s)? in)\s+([A-Z][\w]+(?:\s+[A-Z][\w]+)*)",
)
_LANG = re.compile(r"(?:only\s+)?write(?:s)?\s+([A-Za-z][A-Za-z0-9+#]+)", re.IGNORECASE)


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
    city = _CITY.search(text)
    if city is not None:
        ops.append(
            ExtractedOp(
                subject="user",
                predicate="lives_in",
                object=city.group(1),
                op=OpKind.SET,
                evidence=city.group(0),
            )
        )
    lang = _LANG.search(text)
    if lang is not None:
        kind = OpKind.REPLACE_SET if "only" in lang.group(0).casefold() else OpKind.ADD
        ops.append(
            ExtractedOp(
                subject="user",
                predicate="uses_language",
                object=lang.group(1),
                op=kind,
                evidence=lang.group(0),
            )
        )
    return ExtractionResult(ops=tuple(ops))
