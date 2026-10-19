"""Redact high-confidence secrets from text before storage and extract."""

from __future__ import annotations

import re

REPLACEMENT = "[REDACTED]"

_PEM = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r".+?"
    r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    re.DOTALL,
)
_TOKENS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-=]+"),
)
_ASSIGNMENT = re.compile(r"(?i)\b(?:api[_-]?key|secret|password|token)\s*[:=]\s*\S+")
_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def scrub(text: str) -> str:
    """Replace API keys, passwords, cards, and SSNs with ``[REDACTED]``."""
    redacted = _PEM.sub(REPLACEMENT, text)
    for pattern in _TOKENS:
        redacted = pattern.sub(REPLACEMENT, redacted)
    redacted = _ASSIGNMENT.sub(REPLACEMENT, redacted)
    redacted = _SSN.sub(REPLACEMENT, redacted)
    return _CARD.sub(_card, redacted)


def _card(match: re.Match[str]) -> str:
    digits = "".join(ch for ch in match.group(0) if ch.isdigit())
    if 13 <= len(digits) <= 19 and _luhn(digits):
        return REPLACEMENT
    return match.group(0)


def _luhn(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        n = ord(char) - 48
        if index % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0
