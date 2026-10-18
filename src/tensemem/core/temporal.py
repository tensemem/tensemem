"""Resolve relative dates to valid time, and compare periods (ADR 0005).

The extractor is asked for ISO dates. This module validates that output and
falls back to a small English phrase list when the date is missing or invalid.
Unknown dates use the episode reference time with precision ``unknown``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict

from tensemem.core.clock import INSTANT_WIDTH, format_instant, parse_instant
from tensemem.core.models import ValidPrecision

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_ISO_INSTANT = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[T ]"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:\.(?P<frac>\d+))?(?P<tz>Z|[+-]\d{2}:?\d{2})?$"
)
_ISO_DATE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})$")
_ISO_MONTH = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})$")
_ISO_YEAR = re.compile(r"^(?P<year>\d{4})$")
_EMBEDDED_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_N_AGO = re.compile(r"\b(\d+)\s+(days?|weeks?|months?|years?)\s+ago\b", re.IGNORECASE)
_RELATIVE_DAY = re.compile(r"\b(yesterday|today|tomorrow)\b", re.IGNORECASE)
_LAST_THIS_NEXT = re.compile(r"\b(last|this|next)\s+(week|month|year)\b", re.IGNORECASE)
_LAST_MONTH_NAME = re.compile(rf"\blast\s+({_MONTH_ALT})\b", re.IGNORECASE)
_MONTH_YEAR = re.compile(rf"\b(?:in|since|from)\s+({_MONTH_ALT})\s+(\d{{4}})\b", re.IGNORECASE)
_BARE_MONTH_YEAR = re.compile(rf"\b({_MONTH_ALT})\s+(\d{{4}})\b", re.IGNORECASE)
_IN_YEAR = re.compile(r"\b(?:since|in|from)\s+(\d{4})\b", re.IGNORECASE)
_IN_MONTH = re.compile(rf"\b(?:in|since|from)\s+({_MONTH_ALT})\b", re.IGNORECASE)


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

    Order: ISO in ``value``, English phrases in ``value``, then the same on
    ``evidence``. If nothing parses, use ``reference_time`` as ``unknown``.
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
        phrase = _try_phrase(text, ref)
        if phrase is not None:
            return phrase
        embedded = _try_embedded_iso(text)
        if embedded is not None:
            return embedded
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
    instant = _ISO_INSTANT.match(text)
    if instant is not None:
        parsed = _datetime_from_iso(instant.groupdict())
        return None if parsed is None else _resolved(parsed, ValidPrecision.INSTANT)
    day = _ISO_DATE.match(text)
    if day is not None:
        parsed = _date(int(day["year"]), int(day["month"]), int(day["day"]))
        return None if parsed is None else _resolved(parsed, ValidPrecision.DAY)
    month = _ISO_MONTH.match(text)
    if month is not None:
        parsed = _date(int(month["year"]), int(month["month"]), 1)
        return None if parsed is None else _resolved(parsed, ValidPrecision.MONTH)
    year = _ISO_YEAR.match(text)
    if year is not None:
        parsed = _date(int(year["year"]), 1, 1)
        return None if parsed is None else _resolved(parsed, ValidPrecision.YEAR)
    return None


def _try_embedded_iso(text: str) -> ResolvedTime | None:
    match = _EMBEDDED_DATE.search(text)
    if match is None:
        return None
    return _try_iso(match.group(1))


def _try_phrase(text: str, ref: datetime) -> ResolvedTime | None:
    ago = _N_AGO.search(text)
    if ago is not None:
        return _n_ago(int(ago.group(1)), ago.group(2).casefold(), ref)
    day = _RELATIVE_DAY.search(text)
    if day is not None:
        return _relative_day(day.group(1).casefold(), ref)
    unit = _LAST_THIS_NEXT.search(text)
    if unit is not None:
        return _last_this_next(unit.group(1).casefold(), unit.group(2).casefold(), ref)
    last_month = _LAST_MONTH_NAME.search(text)
    if last_month is not None:
        month = _named_month(ref, last_month.group(1), strict_before=True)
        return _resolved(month, ValidPrecision.MONTH)
    month_year = _MONTH_YEAR.search(text) or _BARE_MONTH_YEAR.search(text)
    if month_year is not None:
        parsed = _date(int(month_year.group(2)), _MONTHS[month_year.group(1).casefold()], 1)
        return None if parsed is None else _resolved(parsed, ValidPrecision.MONTH)
    year = _IN_YEAR.search(text)
    if year is not None:
        parsed = _date(int(year.group(1)), 1, 1)
        return None if parsed is None else _resolved(parsed, ValidPrecision.YEAR)
    in_month = _IN_MONTH.search(text)
    if in_month is not None:
        month = _named_month(ref, in_month.group(1), strict_before=False)
        return _resolved(month, ValidPrecision.MONTH)
    return None


def _n_ago(count: int, unit: str, ref: datetime) -> ResolvedTime:
    if unit.startswith("day"):
        return _resolved(_start_of_day(ref) - timedelta(days=count), ValidPrecision.DAY)
    if unit.startswith("week"):
        return _resolved(_start_of_day(ref) - timedelta(weeks=count), ValidPrecision.DAY)
    if unit.startswith("month"):
        return _resolved(_add_months(_start_of_month(ref), -count), ValidPrecision.MONTH)
    return _resolved(datetime(ref.year - count, 1, 1, tzinfo=UTC), ValidPrecision.YEAR)


def _relative_day(word: str, ref: datetime) -> ResolvedTime:
    day = _start_of_day(ref)
    if word == "yesterday":
        day = day - timedelta(days=1)
    elif word == "tomorrow":
        day = day + timedelta(days=1)
    return _resolved(day, ValidPrecision.DAY)


def _last_this_next(which: str, unit: str, ref: datetime) -> ResolvedTime:
    shift = {"last": -1, "this": 0, "next": 1}[which]
    if unit == "week":
        start = _start_of_iso_week(ref) + timedelta(weeks=shift)
        return _resolved(start, ValidPrecision.DAY)
    if unit == "month":
        return _resolved(_add_months(_start_of_month(ref), shift), ValidPrecision.MONTH)
    return _resolved(datetime(ref.year + shift, 1, 1, tzinfo=UTC), ValidPrecision.YEAR)


def _named_month(ref: datetime, name: str, *, strict_before: bool) -> datetime:
    month = _MONTHS[name.casefold()]
    year = ref.year
    if month > ref.month or (strict_before and month == ref.month):
        year -= 1
    return datetime(year, month, 1, tzinfo=UTC)


def _datetime_from_iso(parts: dict[str, str | None]) -> datetime | None:
    frac = (parts["frac"] or "0").ljust(6, "0")[:6]
    tz = parts["tz"]
    if tz is None or tz == "Z":
        tzinfo: timezone = UTC
    else:
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        hours = int(digits[:2])
        minutes = int(digits[2:4]) if len(digits) >= 4 else 0
        tzinfo = timezone(sign * timedelta(hours=hours, minutes=minutes))
    try:
        instant = datetime(
            int(parts["year"] or 0),
            int(parts["month"] or 0),
            int(parts["day"] or 0),
            int(parts["hour"] or 0),
            int(parts["minute"] or 0),
            int(parts["second"] or 0),
            int(frac),
            tzinfo=tzinfo,
        )
    except ValueError:
        return None
    return instant.astimezone(UTC)


def _date(year: int, month: int, day: int) -> datetime | None:
    try:
        return datetime(year, month, day, tzinfo=UTC)
    except ValueError:
        return None


def _period(valid_from: str, precision: ValidPrecision) -> tuple[datetime, datetime]:
    start = _as_datetime(valid_from)
    if precision is ValidPrecision.INSTANT:
        return start, start + timedelta(microseconds=1)
    if precision is ValidPrecision.DAY:
        day = _start_of_day(start)
        return day, day + timedelta(days=1)
    if precision is ValidPrecision.MONTH:
        month = _start_of_month(start)
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


def _start_of_day(instant: datetime) -> datetime:
    return datetime(instant.year, instant.month, instant.day, tzinfo=UTC)


def _start_of_month(instant: datetime) -> datetime:
    return datetime(instant.year, instant.month, 1, tzinfo=UTC)


def _start_of_iso_week(instant: datetime) -> datetime:
    day = _start_of_day(instant)
    return day - timedelta(days=day.weekday())


def _add_months(instant: datetime, months: int) -> datetime:
    index = instant.year * 12 + (instant.month - 1) + months
    year, month0 = divmod(index, 12)
    return datetime(year, month0 + 1, 1, tzinfo=UTC)


def _resolved(instant: datetime, precision: ValidPrecision) -> ResolvedTime:
    return ResolvedTime(valid_from=format_instant(instant), valid_precision=precision)
