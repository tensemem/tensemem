# Python API

`Memory` is synchronous. `AsyncMemory` mirrors the same methods with `await`.

```python
from tensemem import Memory

mem = Memory("app.db")  # or Memory(llm=..., embedder=...)
mem.register_predicate("lives_in")
mem.register_predicate("uses_language", cardinality="MANY")

added = mem.add("u1", "I live in Delhi")
mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
mem.add_value(user_id="u1", predicate="uses_language", value="Rust")

state = mem.state(user_id="u1")
history = mem.history(user_id="u1", predicate="lives_in")
hits = mem.search(user_id="u1", query="where did I live")
explained = mem.explain(history.facts[-1].id)
ctx = mem.context(user_id="u1", query="plan a weekend")
# ctx.freshness.is_current is False until extract runs.
# Pass llm= and context(..., min_seq=added.seq, wait=1.5) to wait for it.

mem.correct(explained.fact.id, replacement="Pune")
mem.rebuild("u1", wait=True)
print(mem.stats("u1"))
mem.backup("app.bak.db")
dump = mem.export_jsonl("u1")
mem.forget(user_id="u1")
```

## Writes

| Method | Role |
|---|---|
| `add(user_id, text, wait=False)` | Store a message and an extract job |
| `set` / `add_value` / `remove_value` / `replace_values` / `retract` | Typed writes, no LLM |
| `correct(fact_id, replacement=None)` | Reject a never-true fact |
| `flush()` / `add(..., wait=True)` | Drain extract jobs |
| `rebuild(user_id, wait=False)` | Wipe facts, replay the log |
| `forget(user_id)` | Hard-delete a scope |

## Reads

| Method | Role |
|---|---|
| `state` | ACTIVE facts plus freshness |
| `history` | ACTIVE, SUPERSEDED, RETRACTED |
| `explain` | Events, evidence, supersession |
| `search` | Ranked facts and episodes |
| `context` | Packed, fenced prompt block |
| `stats` | Queue depth, counts, token estimate |

## Durability and events

- `backup(path)` uses SQLite's online backup API.
- `export_jsonl` / `import_jsonl` replay predicates and episodes. Public ids change; use `backup()` for a bit-identical copy.
- `Memory(..., hooks=[fn])` or `mem.on(fn)` receives `(event, payload)`. Hook errors are logged and ignored.
- Structured logs go to the `tensemem` logger (`event=extraction scope_id=1 jobs=2`).
- `tensemem mcp` maps `remember` / `recall_context` / `get_state` / `get_history` / `forget` onto this API. See [MCP](mcp.md).
- `tensemem serve` maps the same five operations to HTTP. See [REST](server.md).
