# LangGraph store

`TenseMemStore` is a thin store over one `Memory`. Graphs call `put` / `search`; the engine still extracts and `resolve()` still decides. Needs `tensemem[langgraph]` only to install the framework next to TenseMem — the adapter itself does not import it.

```python
from tensemem import FakeExtractor, Memory
from tensemem.langgraph import TenseMemStore

mem = Memory("app.db", llm=FakeExtractor())
mem.register_predicate("lives_in")
store = TenseMemStore(mem)

store.put(("u1",), "note", {"text": "I live in Delhi"})
hits = store.search(("u1",), query="where do I live")
print(hits[0].value["text"])
print(hits[0].value["freshness"]["is_current"])
```

`namespace[0]` is `user_id`. `namespace[1]` is optional `agent_id`. The engine namespace string is `TenseMemStore(..., namespace="default")`.

## Verbs

| Store call | Engine call |
|---|---|
| `put(namespace, key, {"text": "…"})` | `add()` — `key` is ignored; `content` and `memory` are accepted aliases for `text` |
| `search(namespace, query=…)` | `context()` |
| `get(namespace, "context")` | `context()` |
| `get(namespace, "state")` | `state()` |
| `delete(namespace, "scope")` | `forget()` |

`put` does not SET a predicate named `key`. A mapping with no text field is rejected.

Reads include freshness (`is_current`). Recalled text is fenced so a later `put` of the same conversation does not learn from the model's own echo.
