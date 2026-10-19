"""Redact secrets from text before storage and extract, using detect-secrets."""

from __future__ import annotations

import re

from detect_secrets.core.scan import scan_line
from detect_secrets.settings import transient_settings

REPLACEMENT = "[REDACTED]"

# High-entropy plugins flag ordinary words ("Delhi", "live"). Stick to the
# named credential detectors shipped with detect-secrets.
_PLUGINS = tuple(
    {"name": name}
    for name in (
        "AWSKeyDetector",
        "AzureStorageKeyDetector",
        "BasicAuthDetector",
        "CloudantDetector",
        "DiscordBotTokenDetector",
        "GitHubTokenDetector",
        "GitLabTokenDetector",
        "IbmCloudIamDetector",
        "JwtTokenDetector",
        "KeywordDetector",
        "MailchimpDetector",
        "NpmDetector",
        "OpenAIDetector",
        "PrivateKeyDetector",
        "PypiTokenDetector",
        "SendGridDetector",
        "SlackDetector",
        "SoftlayerDetector",
        "SquareOAuthDetector",
        "StripeDetector",
        "TelegramBotTokenDetector",
        "TwilioKeyDetector",
    )
)
# No input-controlled filters (in particular, comment allowlists).
_SETTINGS = {"plugins_used": list(_PLUGINS), "filters_used": []}
_GITHUB_TOKEN = re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+\b")
_BEGIN_PEM = "-----BEGIN "
_END_PEM = "-----END "


def scrub(text: str) -> str:
    """Replace secrets found by detect-secrets with ``[REDACTED]``."""
    if not text:
        return text
    redacted = text
    seen: set[str] = set()
    github = False
    private_key = False
    with transient_settings(_SETTINGS):
        for line in text.splitlines():
            if not line:
                continue
            for secret in scan_line(line):
                kind = secret.type
                if kind == "GitHub Token":
                    github = True
                    continue
                if kind == "Private Key":
                    private_key = True
                    continue
                value = getattr(secret, "secret_value", None)
                if not isinstance(value, str) or value in seen or value not in redacted:
                    continue
                seen.add(value)
                redacted = redacted.replace(value, REPLACEMENT)
    if github:
        redacted = _GITHUB_TOKEN.sub(REPLACEMENT, redacted)
    if private_key:
        redacted = _redact_pem(redacted)
    return redacted


def _redact_pem(text: str) -> str:
    """Replace each PRIVATE KEY PEM block, including its body, in one forward pass."""
    parts: list[str] = []
    cursor = 0
    while True:
        start = text.find(_BEGIN_PEM, cursor)
        if start < 0:
            parts.append(text[cursor:])
            break
        header_end = text.find("-----", start + len(_BEGIN_PEM))
        header = text[start:header_end] if header_end >= 0 else ""
        if header_end < 0 or "PRIVATE KEY" not in header:
            parts.append(text[cursor : start + len(_BEGIN_PEM)])
            cursor = start + len(_BEGIN_PEM)
            continue
        end = text.find(_END_PEM, header_end + 5)
        if end < 0:
            parts.append(text[cursor:start])
            parts.append(REPLACEMENT)
            break
        tail = text.find("-----", end + len(_END_PEM))
        if tail < 0:
            parts.append(text[cursor:start])
            parts.append(REPLACEMENT)
            break
        parts.append(text[cursor:start])
        parts.append(REPLACEMENT)
        cursor = tail + 5
    return "".join(parts)
