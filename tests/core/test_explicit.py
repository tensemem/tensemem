from tensemem.core.explicit import format_explicit_ops, parse_explicit_ops
from tensemem.core.models import ExtractedOp, OpKind


def test_parse_explicit_ops_skips_deny_and_notes() -> None:
    ops = parse_explicit_ops(
        "SET user.lives_in=Delhi; DENY user.lives_in=Bangalore; "
        "ADD user.uses_language=Rust; NOTE misread a trip"
    )
    assert [(op.op, op.predicate, op.object) for op in ops] == [
        (OpKind.SET, "lives_in", "Delhi"),
        (OpKind.ADD, "uses_language", "Rust"),
    ]


def test_parse_explicit_ops_ignores_free_text() -> None:
    assert parse_explicit_ops("misread a trip as a move") == ()


def test_json_round_trip_keeps_semicolons_in_values() -> None:
    op = ExtractedOp(
        subject="user",
        predicate="uses_language",
        object="Rust; Go",
        op=OpKind.ADD,
        evidence="ADD",
    )
    encoded = format_explicit_ops((op,), note="typo; SET user.lives_in=Paris")
    parsed = parse_explicit_ops(encoded)
    assert [(op.op, op.predicate, op.object) for op in parsed] == [
        (OpKind.ADD, "uses_language", "Rust; Go")
    ]
