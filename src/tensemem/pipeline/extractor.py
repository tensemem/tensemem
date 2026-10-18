"""Call an LLMProvider with the extract_v1 prompt and snapshot."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from tensemem.core.models import ExtractionResult
from tensemem.pipeline.prompt import render_messages
from tensemem.pipeline.snapshot import ExtractSnapshot
from tensemem.providers.llm.base import LLMProvider


def extract(
    provider: LLMProvider,
    snapshot: ExtractSnapshot,
    messages: Sequence[Mapping[str, str]],
) -> ExtractionResult:
    """Ask ``provider`` for typed ops. Does not write facts."""
    return provider.structured(render_messages(snapshot, messages), ExtractionResult)
