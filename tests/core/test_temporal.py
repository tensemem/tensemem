import pytest

from tensemem.core.models import ValidPrecision
from tensemem.core.temporal import (
    is_newer_or_unknown,
    parse_reference_time,
    resolve_valid_time,
)

REF = "2026-10-18T11:00:00.000000Z"


@pytest.mark.parametrize(
    ("value", "evidence", "valid_from", "precision"),
    [
        ("yesterday", "", "2026-10-17T00:00:00.000000Z", ValidPrecision.DAY),
        ("last week", "", "2026-10-11T00:00:00.000000Z", ValidPrecision.DAY),
        ("in March", "", "2026-03-01T00:00:00.000000Z", ValidPrecision.DAY),
        ("2026-03-01", "", "2026-03-01T00:00:00.000000Z", ValidPrecision.DAY),
        ("2026-03", "", "2026-03-01T00:00:00.000000Z", ValidPrecision.MONTH),
        ("2026", "", "2026-01-01T00:00:00.000000Z", ValidPrecision.YEAR),
        ("3 days ago", "", "2026-10-15T00:00:00.000000Z", ValidPrecision.DAY),
        ("last month", "", "2026-09-18T00:00:00.000000Z", ValidPrecision.DAY),
        (None, "I moved last week", REF, ValidPrecision.UNKNOWN),
        (None, "I may move", REF, ValidPrecision.UNKNOWN),
        (None, "no date here", REF, ValidPrecision.UNKNOWN),
        ("2026-02-31", "", REF, ValidPrecision.UNKNOWN),
    ],
)
def test_resolve_valid_time(
    value: str | None, evidence: str, valid_from: str, precision: ValidPrecision
) -> None:
    resolved = resolve_valid_time(value, reference_time=REF, evidence=evidence)
    assert resolved.valid_from == valid_from
    assert resolved.valid_precision is precision


def test_iso_instant_and_offset_normalize_to_utc() -> None:
    instant = resolve_valid_time("2026-10-10T12:30:00.123456Z", reference_time=REF)
    offset = resolve_valid_time("2026-10-10T15:30:00+05:30", reference_time=REF)
    assert instant.valid_from == "2026-10-10T12:30:00.123456Z"
    assert instant.valid_precision is ValidPrecision.INSTANT
    assert offset.valid_from == "2026-10-10T10:00:00.000000Z"


def test_parse_reference_time_accepts_date_and_instant() -> None:
    assert parse_reference_time("2026-10-18").isoformat() == "2026-10-18T00:00:00+00:00"
    assert parse_reference_time(REF).isoformat() == "2026-10-18T11:00:00+00:00"
    with pytest.raises(ValueError, match="invalid reference_time"):
        parse_reference_time("next Tuesday-ish")


def test_overlapping_periods_are_newer() -> None:
    assert is_newer_or_unknown(
        "2026-10-10T00:00:00.000000Z",
        ValidPrecision.DAY,
        "2026-10-01T00:00:00.000000Z",
        ValidPrecision.MONTH,
    )
    assert not is_newer_or_unknown(
        "2025-01-01T00:00:00.000000Z",
        ValidPrecision.YEAR,
        "2026-06-01T00:00:00.000000Z",
        ValidPrecision.DAY,
    )
    assert is_newer_or_unknown(
        None, ValidPrecision.DAY, "2026-01-01T00:00:00.000000Z", ValidPrecision.DAY
    )
