from tensemem.core.models import ExtractedOp, ExtractionResult, OpKind
from tensemem.providers.llm import FakeExtractor


def test_rule_extract_move_and_only_language() -> None:
    fake = FakeExtractor()
    result = fake.structured(
        [{"role": "user", "content": "I moved to Bangalore last week and now only write Rust."}],
        ExtractionResult,
    )
    assert [op.predicate for op in result.ops] == ["lives_in", "uses_language"]
    assert result.ops[0].object == "Bangalore"
    assert result.ops[0].op is OpKind.SET
    assert result.ops[1].object == "Rust"
    assert result.ops[1].op is OpKind.REPLACE_SET
    assert len(fake.calls) == 1


def test_only_elsewhere_does_not_replace_language() -> None:
    fake = FakeExtractor()
    result = fake.structured(
        [{"role": "user", "content": "I only moved to Bangalore and write Rust."}],
        ExtractionResult,
    )
    lang = next(op for op in result.ops if op.predicate == "uses_language")
    assert lang.op is OpKind.ADD


def test_hedge_and_third_party_and_retract() -> None:
    fake = FakeExtractor()
    silent = fake.structured(
        [{"role": "user", "content": "If I moved to Goa next year that would be nice"}],
        ExtractionResult,
    )
    assert silent.ops == ()
    wife = fake.structured(
        [{"role": "user", "content": "My wife lives in Mumbai"}],
        ExtractionResult,
    )
    assert wife.ops[0].subject == "user.wife"
    assert wife.ops[0].object == "Mumbai"
    retract = fake.structured(
        [{"role": "user", "content": "I don't live in Delhi anymore"}],
        ExtractionResult,
    )
    assert retract.ops[0].op is OpKind.RETRACT
    deny = fake.structured(
        [{"role": "user", "content": "I never lived in Pune"}],
        ExtractionResult,
    )
    assert deny.ops[0].op is OpKind.DENY


def test_scripted_queue_and_mapping() -> None:
    queued = ExtractionResult(
        ops=(
            ExtractedOp(
                subject="user",
                predicate="diet",
                object="vegetarian",
                op=OpKind.SET,
                evidence="I'm vegetarian",
            ),
        )
    )
    by_queue = FakeExtractor([queued])
    first = by_queue.structured([{"role": "user", "content": "anything"}], ExtractionResult)
    assert first.ops[0].object == "vegetarian"

    mapped = FakeExtractor({"I live in Pune": queued})
    hit = mapped.structured([{"role": "user", "content": "I live in Pune"}], ExtractionResult)
    assert hit.ops[0].predicate == "diet"
    miss = mapped.structured([{"role": "user", "content": "I live in Delhi"}], ExtractionResult)
    assert miss.ops[0].object == "Delhi"
