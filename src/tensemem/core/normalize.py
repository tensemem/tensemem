"""Normalization used for registry names and alias lookups."""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[\W_]+")
_WHITESPACE = re.compile(r"\s+")


def normalize_key(text: str) -> str:
    """Snake-case identifier for predicate names: ``"Home City"`` -> ``"home_city"``."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return _NON_WORD.sub("_", folded).strip("_")


def normalize_value(text: str) -> str:
    """Comparison key for values and entity aliases: ``" VS  Code "`` -> ``"vs code"``.

    Punctuation is kept so ``"C++"``, ``"C#"`` and ``"C"`` stay distinct.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    return _WHITESPACE.sub(" ", folded).strip()
