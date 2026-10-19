from tensemem.security.scrub import REPLACEMENT, scrub


def test_scrub_redacts_tokens_and_keeps_plain_speech() -> None:
    text = "I live in Delhi sk-abcdefghijklmnopqrstuvwxyz123456"
    out = scrub(text)
    assert "Delhi" in out
    assert "sk-abcdefgh" not in out
    assert REPLACEMENT in out


def test_scrub_redacts_password_assignment_and_valid_card() -> None:
    text = "password=hunter2 card 4111111111111111 ssn 123-45-6789"
    out = scrub(text)
    assert "hunter2" not in out
    assert "4111111111111111" not in out
    assert "123-45-6789" not in out
    assert out.count(REPLACEMENT) == 3


def test_scrub_ignores_non_luhn_digit_runs() -> None:
    text = "order 4111111111111112"
    assert scrub(text) == text
