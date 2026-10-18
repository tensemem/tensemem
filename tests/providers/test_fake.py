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
