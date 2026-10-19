"""Ingestion: qualification gate, extraction, normalization, and the job worker."""

from tensemem.pipeline.extractor import extract
from tensemem.pipeline.guard import keep_ops, looks_like_confirmation, user_span
from tensemem.pipeline.normalize import normalize_ops
from tensemem.pipeline.policy import apply_policy, planned_predicate
from tensemem.pipeline.prompt import PROMPT_VERSION, render_messages
from tensemem.pipeline.snapshot import (
    CompactFact,
    ExtractSnapshot,
    RegistryEntry,
    load_extract_snapshot,
)
from tensemem.pipeline.worker import process_one, qualifies

__all__ = [
    "PROMPT_VERSION",
    "CompactFact",
    "ExtractSnapshot",
    "RegistryEntry",
    "apply_policy",
    "extract",
    "keep_ops",
    "load_extract_snapshot",
    "looks_like_confirmation",
    "normalize_ops",
    "planned_predicate",
    "process_one",
    "qualifies",
    "render_messages",
    "user_span",
]
