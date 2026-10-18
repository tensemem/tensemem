"""Resolve relative dates to valid time, and compare periods (ADR 0005).

ISO strings are classified here so we know the precision (year / month / day /
instant). English phrases go to ``dateparser``. Unknown dates use the episode
reference time with precision ``unknown``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import dateparser
from dateparser.search import search_dates
from pydantic import BaseModel, ConfigDict

from tensemem.core.clock import INSTANT_WIDTH, format_instant, parse_instant
from tensemem.core.models import ValidPrecision

_MONTH_ONLY = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)$",
    re.IGNORECASE,
)
_YEAR_PHRASE = re.compile(r"^(?:since|in|from)?\s*\d{4}$", re.IGNORECASE)
_MONTH_WORD = re.compile(
    r"\b(months?|january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
    re.IGNORECASE,
)


class ResolvedTime(BaseModel):
    """A valid-time instant plus how precisely the text supported it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    valid_from: str
    valid_precision: ValidPrecision


def parse_reference_time(text: str) -> datetime:
    """Parse an episode ``occurred_at`` or a developer-supplied reference time."""
    raw = text.strip()
    if len(raw) == INSTANT_WIDTH and raw.endswith("Z"):
        return parse_instant(raw)
    parsed = _try_iso(raw)
    if parsed is None:
        msg = f"invalid reference_time: {text!r}"
        raise ValueError(msg)
    return parse_instant(parsed.valid_from)


def resolve_valid_time(
    value: str | None,
    *,
    reference_time: str,
    evidence: str = "",
) -> ResolvedTime:
    """Turn an extractor date or a phrase into storage-form valid time.

    Order: ISO in ``value``, ``dateparser`` on ``value``, then ``dateparser``
    search on ``evidence``. If nothing parses, use ``reference_time`` as
    ``unknown``.
    """
    ref = parse_reference_time(reference_time)
    if value is not None and value.strip():
        text = value.strip()
        iso = _try_iso(text)
        if iso is not None:
            return iso
        parsed = _from_dateparser(text, ref, allow_month_only=True)
        if parsed is not None:
            return parsed
    if evidence.strip():
        parsed = _from_dateparser(evidence, ref, allow_month_only=False)
        if parsed is not None:
            return parsed
    return ResolvedTime(valid_from=format_instant(ref), valid_precision=ValidPrecision.UNKNOWN)


def is_newer_or_unknown(
    new_from: str | None,
    new_precision: ValidPrecision,
    old_from: str | None,
    old_precision: ValidPrecision,
) -> bool:
    """True when the new fact should supersede (newer, overlapping, or unknown)."""
    if new_from is None or old_from is None:
        return True
    if new_precision is ValidPrecision.UNKNOWN or old_precision is ValidPrecision.UNKNOWN:
        return True
    try:
        new_start, new_end = _period(new_from, new_precision)
        old_start, old_end = _period(old_from, old_precision)
    except ValueError:
        return True
    if new_start < old_end and old_start < new_end:
        return True
    return new_start >= old_start


def _try_iso(text: str) -> ResolvedTime | None:
    """Parse a whole-string ISO date so precision comes from the shape, not a guess."""
    if len(text) == 4 and text.isdigit():
        return _date(int(text), 1, 1, ValidPrecision.YEAR)
    if len(text) == 7 and text[4] == "-":
        try:
            return _date(int(text[:4]), int(text[5:7]), 1, ValidPrecision.MONTH)
        except ValueError:
            return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            day = datetime.fromisoformat(text).replace(tzinfo=UTC)
        except ValueError:
            return None
        return _resolved(day, ValidPrecision.DAY)
    if "T" in text:
        try:
            instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        return _resolved(instant.astimezone(UTC), ValidPrecision.INSTANT)
    return None


def _from_dateparser(text: str, ref: datetime, *, allow_month_only: bool) -> ResolvedTime | None:
    settings = _settings(ref)
    parsed = dateparser.parse(text, languages=["en"], settings=settings)
    if parsed is not None:
        return _from_parsed(text, parsed)
    found = search_dates(text, languages=["en"], settings=settings)
    if not found:
        return None
    for match, instant in found:
        if allow_month_only or not _MONTH_ONLY.fullmatch(match.strip()):
            return _from_parsed(match, instant)
    return None


def _from_parsed(match: str, instant: datetime) -> ResolvedTime:
    instant = instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)
    precision = _precision_from_match(match)
    if precision is ValidPrecision.YEAR:
        instant = datetime(instant.year, 1, 1, tzinfo=UTC)
    elif precision is ValidPrecision.MONTH:
        instant = datetime(instant.year, instant.month, 1, tzinfo=UTC)
    elif precision is ValidPrecision.DAY:
        instant = datetime(instant.year, instant.month, instant.day, tzinfo=UTC)
    return _resolved(instant, precision)


def _precision_from_match(text: str) -> ValidPrecision:
    iso = _try_iso(text.strip())
    if iso is not None:
        return iso.valid_precision
    folded = text.strip()
    if _YEAR_PHRASE.fullmatch(folded):
        return ValidPrecision.YEAR
    if _MONTH_WORD.search(folded):
        return ValidPrecision.MONTH
    return ValidPrecision.DAY


def _settings(ref: datetime) -> dict[str, Any]:
    return {
        "RELATIVE_BASE": ref.replace(tzinfo=None),
        "TIMEZONE": "UTC",
        "TO_TIMEZONE": "UTC",
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "past",
        "PREFER_DAY_OF_MONTH": "first",
    }


def _date(year: int, month: int, day: int, precision: ValidPrecision) -> ResolvedTime | None:
    try:
        return _resolved(datetime(year, month, day, tzinfo=UTC), precision)
    except ValueError:
        return None


def _period(valid_from: str, precision: ValidPrecision) -> tuple[datetime, datetime]:
    start = _as_datetime(valid_from)
    if precision is ValidPrecision.INSTANT:
        return start, start + timedelta(microseconds=1)
    if precision is ValidPrecision.DAY:
        day = datetime(start.year, start.month, start.day, tzinfo=UTC)
        return day, day + timedelta(days=1)
    if precision is ValidPrecision.MONTH:
        month = datetime(start.year, start.month, 1, tzinfo=UTC)
        return month, _add_months(month, 1)
    if precision is ValidPrecision.YEAR:
        year = datetime(start.year, 1, 1, tzinfo=UTC)
        return year, datetime(start.year + 1, 1, 1, tzinfo=UTC)
    msg = f"precision {precision} has no closed period"
    raise ValueError(msg)


def _as_datetime(text: str) -> datetime:
    if len(text) == INSTANT_WIDTH and text.endswith("Z"):
        return parse_instant(text)
    return parse_reference_time(text)


def _add_months(instant: datetime, months: int) -> datetime:
    index = instant.year * 12 + (instant.month - 1) + months
    year, month0 = divmod(index, 12)
    return datetime(year, month0 + 1, 1, tzinfo=UTC)


def _resolved(instant: datetime, precision: ValidPrecision) -> ResolvedTime:
    return ResolvedTime(valid_from=format_instant(instant), valid_precision=precision)
