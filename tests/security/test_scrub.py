from tensemem.security.scrub import REPLACEMENT, scrub


def test_scrub_keeps_plain_speech() -> None:
    assert scrub("I live in Delhi") == "I live in Delhi"


def test_scrub_redacts_provider_tokens() -> None:
    openai = "sk-" + "Xi8tcNiHV9awbCcvilTe" + "T3BlbkFJ" + "3UDnpdEwNNm6wVBpYM0o"
    aws = "AKIA" + "IOSFODNN7EXAMPLE"
    slack = "xoxb-" + "123456789012-123456789012-" + "abcdefghijklmnopqrstuvwx"
    text = f"I live in Delhi {openai} {aws} {slack}"
    out = scrub(text)
    assert "Delhi" in out
    assert openai not in out
    assert aws not in out
    assert slack not in out
    assert REPLACEMENT in out


def test_scrub_redacts_quoted_password_assignment() -> None:
    out = scrub('password = "hunter2"')
    assert "hunter2" not in out
    assert REPLACEMENT in out


def test_scrub_ignores_allowlist_pragma() -> None:
    out = scrub('password = "hunter2"  # pragma: allowlist secret')
    assert "hunter2" not in out
    assert REPLACEMENT in out


def test_scrub_redacts_github_token_and_private_key_block() -> None:
    token = "ghp_" + ("a" * 36)
    kind = "RSA " + "PRIVATE KEY"
    begin = f"-----BEGIN {kind}-----"
    end = f"-----END {kind}-----"
    body = "MIIEogIBAAKCAQEAnexamplebody"
    pem = f"{begin}\n{body}\n{end}"
    out = scrub(f"token {token}\n{pem}")
    assert token not in out
    assert begin not in out
    assert body not in out
    assert REPLACEMENT in out
