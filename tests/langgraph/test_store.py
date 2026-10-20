import pytest

from tensemem import FakeExtractor, Memory
from tensemem.langgraph import CONTEXT_KEY, SCOPE_KEY, STATE_KEY, TenseMemStore
from tensemem.mcp import seed_starter


def test_put_search_state_and_forget() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        store = TenseMemStore(mem)
        store.put(("u1",), "ignored", {"text": "I live in Delhi"})
        store.put(("u1",), "ignored", {"memory": "I moved to Bangalore"})
        hits = store.search(("u1",), query="where do I live")
        assert len(hits) == 1
        assert hits[0].key == CONTEXT_KEY
        assert "Bangalore" in str(hits[0].value["text"])
        freshness = hits[0].value["freshness"]
        assert isinstance(freshness, dict)
        assert freshness["is_current"] is True

        state = store.get(("u1",), STATE_KEY)
        assert state is not None
        values = state.value["values"]
        assert isinstance(values, dict)
        assert values["lives_in"] == "Bangalore"
        assert store.get(("u1",), CONTEXT_KEY) is not None
        assert store.get(("u1",), "unknown") is None

        store.delete(("u1",), SCOPE_KEY)
        empty = store.get(("u1",), STATE_KEY)
        assert empty is not None
        assert empty.value["values"] == {}


def test_put_rejects_slot_maps_and_empty_user() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        store = TenseMemStore(mem)
        with pytest.raises(ValueError, match=r"value\.text"):
            store.put(("u1",), "lives_in", {"object": "Delhi"})
        with pytest.raises(ValueError, match="user_id"):
            store.put((), "k", {"text": "I live in Delhi"})
        with pytest.raises(ValueError, match="scope"):
            store.delete(("u1",), "context")
