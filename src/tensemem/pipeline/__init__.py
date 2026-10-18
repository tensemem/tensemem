"""Ingestion: qualification gate, extraction, normalization, and the job worker."""

from tensemem.pipeline.extractor import extract
from tensemem.pipeline.normalize import normalize_ops
from tensemem.pipeline.prompt import PROMPT_VERSION, render_messages
from tensemem.pipeline.snapshot import (
    CompactFact,
    ExtractSnapshot,
    RegistryEntry,
    load_extract_snapshot,
)

__all__ = [
    "PROMPT_VERSION",
    "CompactFact",
    "ExtractSnapshot",
    "RegistryEntry",
    "extract",
    "load_extract_snapshot",
    "normalize_ops",
    "render_messages",
]
