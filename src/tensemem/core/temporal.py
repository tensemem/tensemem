"""Resolve relative dates to valid time, and compare periods (ADR 0005).

ISO strings are classified here so we know the precision (year / month / day /
instant). English phrases go to ``dateparser`` and are stored as a day.
Unknown dates use the episode reference time with precision ``unknown``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import dateparser
from pydantic import BaseModel, ConfigDict

from tensemem.core.clock import INSTANT_WIDTH, format_instant, parse_instant
from tensemem.core.models import ValidPrecision


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

    ``dateparser`` is only asked to parse the date field (or the evidence
    string as a whole). It is not asked to hunt for dates inside a sentence.
    """
    ref = parse_reference_time(reference_time)
    for candidate in (value, evidence):
        if candidate is None:
            continue
        text = candidate.strip()
        if not text:
            continue
        iso = _try_iso(text)
        if iso is not None:
            return iso
        parsed = dateparser.parse(text, languages=["en"], settings=_settings(ref))
        if parsed is not None:
            return _as_day(parsed)
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


def _as_day(instant: datetime) -> ResolvedTime:
    utc = instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)
    return _resolved(datetime(utc.year, utc.month, utc.day, tzinfo=UTC), ValidPrecision.DAY)


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
