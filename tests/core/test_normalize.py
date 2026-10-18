import pytest

from tensemem.core.normalize import normalize_key, normalize_value


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("lives_in", "lives_in"),
        ("Home City", "home_city"),
        ("  Preferred-IDE ", "preferred_ide"),
        ("São Paulo", "são_paulo"),
    ],
)
def test_normalize_key(text: str, expected: str) -> None:
    assert normalize_key(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (" VS  Code ", "vs code"),
        ("PostgreSQL", "postgresql"),
        ("C++", "c++"),
        ("C#", "c#"),
    ],
)
def test_normalize_value_keeps_punctuation(text: str, expected: str) -> None:
    assert normalize_value(text) == expected
