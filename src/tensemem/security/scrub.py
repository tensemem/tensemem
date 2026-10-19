"""Redact secrets from text before storage and extract, using detect-secrets."""

from __future__ import annotations

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
_SETTINGS = {"plugins_used": list(_PLUGINS)}
# GitHubTokenDetector sometimes yields only the three-letter prefix.
_MIN_SECRET_LEN = 6


def scrub(text: str) -> str:
    """Replace secrets found by detect-secrets with ``[REDACTED]``."""
    if not text:
        return text
    redacted = text
    seen: set[str] = set()
    with transient_settings(_SETTINGS):
        for line in text.splitlines():
            if not line:
                continue
            for secret in scan_line(line):
                value = getattr(secret, "secret_value", None)
                if not isinstance(value, str) or len(value) < _MIN_SECRET_LEN or value in seen:
                    continue
                seen.add(value)
                redacted = redacted.replace(value, REPLACEMENT)
    return redacted
