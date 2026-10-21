"""First run: no API key. Same path as the README."""

from tensemem import FakeExtractor, Memory

with Memory(":memory:", llm=FakeExtractor()) as mem:
    mem.register_predicate("lives_in")
    added = mem.add("u1", "I live in Delhi")
    ctx = mem.context(user_id="u1", min_seq=added.seq, wait=1.5)
    print(ctx.text)
    print("current:", ctx.freshness.is_current)
    mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
    print(mem.state("u1").values)
