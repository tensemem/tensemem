from pathlib import Path

from tensemem import FakeExtractor
from tensemem.core.models import ExtractedOp, OpKind
from tensemem.eval.golden import GoldOp, evaluate, load_cases, score_ops

_V1 = Path(__file__).with_name("v1.jsonl")


def test_fake_extractor_hits_every_scored_case() -> None:
    cases = load_cases(_V1)
    report = evaluate(FakeExtractor(), cases, skip_fake=True)
    assert report.cases >= 10
    assert report.skipped >= 1
    assert report.precision == 1.0
    assert report.recall == 1.0
    assert "move" in report.by_category
    assert "language" in report.by_category
    assert "chitchat" in report.by_category


def test_skip_fake_cases_are_labeled() -> None:
    cases = load_cases(_V1)
    skipped = [case for case in cases if case.skip_fake]
    assert {case.category for case in skipped} >= {
        "deny",
        "retract",
        "hypothetical",
        "confirmation",
        "third_party",
        "diet",
    }


def test_score_ops_is_a_set_match() -> None:
    expected = (
        GoldOp(predicate="lives_in", object="Delhi"),
        GoldOp(predicate="uses_language", object="Rust", op=OpKind.REPLACE_SET),
    )
    predicted = (
        ExtractedOp(
            subject="user",
            predicate="lives_in",
            object="Delhi",
            op=OpKind.SET,
            evidence="I live in Delhi",
        ),
        ExtractedOp(
            subject="user",
            predicate="lives_in",
            object="Delhi",
            op=OpKind.SET,
            evidence="I live in Delhi",
        ),
        ExtractedOp(
            subject="user",
            predicate="uses_language",
            object="Python",
            op=OpKind.ADD,
            evidence="write Python",
        ),
    )
    tp, fp, fn = score_ops(expected, predicted)
    assert (tp, fp, fn) == (1, 1, 1)
