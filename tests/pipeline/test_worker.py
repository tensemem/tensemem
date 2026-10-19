from tensemem.pipeline.worker import qualifies


def test_qualifies_requires_letters_or_digits() -> None:
    assert qualifies("I live in Delhi")
    assert qualifies("room 12")
    assert not qualifies("")
    assert not qualifies("   ")
    assert not qualifies("???")
