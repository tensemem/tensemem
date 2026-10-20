# LlamaIndex chat memory

`TenseMemChatMemory` is a thin chat memory over one `Memory`. Call `put` / `get` directly, or `await chat.aput(...)` / `await chat.aget(...)`. The adapter does not subclass a framework memory ABC. The engine still extracts and `resolve()` still decides. Needs `tensemem[llamaindex]` only to install the framework next to TenseMem — the adapter itself does not import it.

```python
from tensemem import FakeExtractor, Memory
from tensemem.llamaindex import TenseMemChatMemory

mem = Memory("app.db", llm=FakeExtractor())
mem.register_predicate("lives_in")
chat = TenseMemChatMemory(mem)

chat.put("u1", "I live in Pune")
ctx = chat.get("u1", "where do I live")
print(ctx.text)
print(ctx.freshness.is_current)
```

`put` ingests user text. It does not SET a predicate. Recalled text is fenced so a later `put` of the same conversation does not learn from the model's own echo.
