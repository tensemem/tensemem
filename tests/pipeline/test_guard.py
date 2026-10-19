from tensemem.core.models import ExtractedOp, OpKind
from tensemem.pipeline.guard import keep_ops, user_span
from tensemem.security.fence import wrap


def test_user_span_removes_fenced_echo() -> None:
    block = wrap("- `lives in`: `Delhi`", "abc123")
    mixed = user_span(block + "I moved to Bangalore", "abc123")
    assert user_span(block, "abc123").strip() == ""
    assert "Delhi" not in mixed
    assert "I moved to Bangalore" in mixed


def test_keep_ops_requires_verbatim_evidence() -> None:
    span = "I live in Delhi"
    kept = keep_ops((_op("Delhi", evidence="I live in Delhi"),), span)
    dropped = keep_ops((_op("Pune", evidence="I live in Pune"),), span)
    empty = keep_ops((_op("Delhi", evidence=""),), span)
    assert [op.object for op in kept] == ["Delhi"]
    assert dropped == ()
    assert empty == ()


def test_keep_ops_leaves_confirmation_to_the_extractor() -> None:
    flagged = keep_ops((_op("Delhi", evidence="yes", is_confirmation=True),), "yes")
    plain = keep_ops((_op("Delhi", evidence="I live in Delhi"),), "I live in Delhi")
    assert flagged[0].is_confirmation
    assert plain[0].is_confirmation is False


def _op(city: str, *, evidence: str, is_confirmation: bool = False) -> ExtractedOp:
    return ExtractedOp(
        subject="user",
        predicate="lives_in",
        object=city,
        op=OpKind.SET,
        evidence=evidence,
        is_confirmation=is_confirmation,
    )
