"""Render extract_v1 system text around a snapshot."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from importlib import resources

from tensemem.pipeline.snapshot import CompactFact, ExtractSnapshot, RegistryEntry

PROMPT_VERSION = "extract_v1"


def render_messages(
    snapshot: ExtractSnapshot,
    messages: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """System prompt plus the conversation, ready for ``LLMProvider.structured``."""
    system = _template().format(
        reference_time=snapshot.reference_time,
        registry=_format_registry(snapshot.registry),
        current_state=_format_facts(snapshot.facts),
    )
    rendered = [{"role": "system", "content": system}]
    for message in messages:
        rendered.append({"role": message["role"], "content": message["content"]})
    return rendered


def _template() -> str:
    return (
        resources.files("tensemem.pipeline")
        .joinpath("prompts/extract_v1.md")
        .read_text(encoding="utf-8")
    )


def _format_registry(entries: Sequence[RegistryEntry]) -> str:
    if not entries:
        return "(none)"
    lines: list[str] = []
    for item in entries:
        lines.append(
            "<registry_entry>"
            f"<name>{_field(item.name)}</name>"
            f"<cardinality>{_field(item.cardinality.value)}</cardinality>"
            f"<description>{_field(item.description)}</description>"
            "</registry_entry>"
        )
    return "\n".join(lines)


def _format_facts(facts: Sequence[CompactFact]) -> str:
    if not facts:
        return "(none)"
    return "\n".join(
        "<fact>"
        f"<subject>{_field(fact.subject)}</subject>"
        f"<predicate>{_field(fact.predicate)}</predicate>"
        f"<object>{_field(fact.object)}</object>"
        "</fact>"
        for fact in facts
    )


def _field(text: str) -> str:
    """Flatten and escape a stored field so it cannot change prompt structure."""
    flat = " ".join(text.split())
    return escape(flat, quote=True).replace("{", "&#123;").replace("}", "&#125;")
