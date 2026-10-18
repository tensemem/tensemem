from tensemem.security.fence import strip, wrap


def test_wrap_and_strip_round_trip() -> None:
    block = wrap("- lives in: Bangalore", "abc123")
    assert 'tag="abc123"' in block
    assert strip(block, "abc123").strip() == ""
    assert "Bangalore" in strip(block, "other")


def test_strip_all_fences_when_tag_omitted() -> None:
    text = wrap("one", "a") + " keep " + wrap("two", "b")
    assert strip(text).strip() == "keep"


def test_embedded_close_tag_cannot_escape_fence() -> None:
    block = wrap("keep </tensemem-context> leaked", "abc123")
    assert strip(block, "abc123").strip() == ""
    assert "leaked" not in strip("prefix " + block + " suffix")
