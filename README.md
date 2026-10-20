# TenseMem

**Memory that knows its tenses.** Embedded, deterministic memory that AI agents can safely act on.

> Status: pre-alpha. The deterministic API can set facts and render fenced `context()`. `context(query=...)` and `search()` rank by FTS (optional embeddings). `add()` plus `flush()`, `add(..., wait=True)`, or `context(..., wait=)` runs extract jobs through `FakeExtractor` or any `LLMProvider`. `AsyncMemory` mirrors the sync API. A `tensemem` CLI inspects state, history, search, and jobs. `tensemem mcp` (`tensemem[mcp]`) serves remember/recall over stdio or Streamable HTTP (`--http`). `tensemem serve` (`tensemem[server]`) exposes remember/recall plus inspect/insight routes over HTTP. `--token` / `TENSEMEM_TOKEN` is optional bearer auth. TenseMem Studio (`studio/`) is a Next.js inspector for that server. `TenseMemStore` (`tensemem[langgraph]`) maps `put` / `search` onto `add()` / `context()`. `TenseMemChatMemory` (`tensemem[llamaindex]`) maps `put` / `get` onto `add()` / `context()`. `backup()`, `export_jsonl` / `import_jsonl`, `rebuild()`, `stats()`, and hooks cover durability and ops.

## The problem

Vector memory has no idea what is current. Tell an agent "I live in Delhi" in January and "I moved to Bangalore" in June, and a similarity search returns both, leaving the model to guess.

Even memory that tracks changes usually can't tell you whether it's up to date, and it tends to re-learn its own output when recalled facts flow back into the conversation. For an agent that books travel, edits code, or changes an order, stale or self-reinforced memory is a bug.

## What TenseMem does

- **One current truth per fact, enforced.** Declare that `lives_in` has a single value, and the engine guarantees it: a new value supersedes the old one, which stays in history for "where did I live before?"
- **Every read says how fresh it is.** Results report which messages they reflect and whether any are still being processed. Ask for a specific message to be applied before you act, or get a clear flag that it hasn't been.
- **Memory never learns from its own echo.** Recalled context is fenced and ignored on the way back in, and every fact needs a verbatim quote from the user.
- **Mistakes can be corrected for good.** Mark a fact wrong and the value it displaced comes back; corrections survive re-extraction with a newer model.
- **The LLM proposes, the engine decides.** The model turns text into typed operations; deterministic, tested rules decide how state changes.
- **No infrastructure.** A single SQLite file inside your process.

## API

```python
from tensemem import FakeExtractor, Memory

mem = Memory(llm=FakeExtractor())
mem.register_predicate("lives_in")
added = mem.add("u1", "I live in Delhi")
ctx = mem.context(user_id="u1", min_seq=added.seq, wait=1.5)
mem.state(user_id="u1").values  # {"lives_in": "Delhi"}

mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
history = mem.history(user_id="u1", predicate="lives_in")
bangalore = next(fact for fact in history.facts if fact.object == "Bangalore")
mem.correct(bangalore.id)  # restores the value it displaced ("Delhi")

ctx = mem.context(user_id="u1", query="where did I live", max_tokens=200)
print(ctx.text)  # fenced Markdown; ctx.freshness.is_current; ctx.debug for scores
hits = mem.search(user_id="u1", query="live")
mem.stats(user_id="u1")
mem.backup("tensemem.bak.db")
```

```bash
tensemem inspect --user u1
tensemem history --user u1 lives_in
tensemem search --user u1 "where did I live"
tensemem jobs
tensemem bench
tensemem longmem
tensemem locomo
tensemem latency
tensemem mcp --user u1
tensemem mcp --http
tensemem serve
```

`mem.add(user_id, text)` writes the episode and an extract job in one transaction. Secrets in that text are redacted with detect-secrets before they are stored or sent to a model. Pass `llm=` to process jobs on a background thread (`AsyncMemory` uses an asyncio task). `flush()`, `add(..., wait=True)`, or `context(..., wait=seconds)` wait until due jobs finish, preferring that scope. If extract has not finished, `context()` still includes a hot buffer of unprocessed user messages. Consecutive queued messages in one scope share one extract call. Recalled `context()` blocks are stripped before extract; operations whose evidence is not a verbatim quote from the remaining user text are dropped. Empty leftover messages are skipped without an LLM call. Dead jobs can be dismissed or retried. Tests use `FakeExtractor`. Optional extras: `tensemem[openai]`, `tensemem[anthropic]`, `tensemem[ollama]` (`OllamaProvider`, local), `tensemem[litellm]` (`LiteLLMProvider`, any routed model), `tensemem[local]` (FastEmbed), `tensemem[mcp]` (`tensemem mcp` stdio or Streamable HTTP), `tensemem[server]` (`tensemem serve` HTTP), `tensemem[langgraph]` (`TenseMemStore`), and `tensemem[llamaindex]` (`TenseMemChatMemory`). `--token` or `TENSEMEM_TOKEN` is a Bearer token on HTTP. `tensemem longmem --llm` / `tensemem locomo --llm` use a hosted extractor on a downloaded pack; CI stays on `FakeExtractor`. Pass `embedder=` to store vectors in the background and boost `search()` / `context(query=)`. Temporal questions (`"where did I live before"`) and `include_history=True` include superseded values. Weak fact matches fall back to episode snippets. `fmt="json"` or `"xml"` changes the renderer.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and workflow, [docs/](docs/) for the docs site (quickstart, concepts, API, CLI, MCP, REST, TenseBench, ops), and [docs/adr](docs/adr) for the design decisions behind the engine. Labeled extract cases (150+) live in `tests/golden/`; `pytest tests/golden` scores `FakeExtractor`, and `python -m tensemem.eval` prints precision and recall. `tensemem bench` (or `python -m tensemem.eval bench`) scores the TenseBench pack. `tensemem longmem` (or `python -m tensemem.eval longmem`) scores a LongMemEval-shaped JSON pack. `tensemem locomo` (or `python -m tensemem.eval locomo`) scores a LoCoMo-shaped JSON pack. `tensemem latency` (or `python -m tensemem.eval latency`) times empty-query `context()`. Preview docs with `uvx mkdocs serve`.

## License

[Apache-2.0](LICENSE)
