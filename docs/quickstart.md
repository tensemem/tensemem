# Quickstart

```python
from tensemem import FakeExtractor, Memory

mem = Memory(llm=FakeExtractor())
mem.register_predicate("lives_in")
added = mem.add("u1", "I live in Delhi")
ctx = mem.context(user_id="u1", min_seq=added.seq, wait=1.5)
print(ctx.text)
print(ctx.freshness.is_current)
```

`FakeExtractor` is rule-based and needs no API key. For a real model, pass any `LLMProvider` (`tensemem[openai]`, `tensemem[anthropic]`, `tensemem[ollama]`, `tensemem[litellm]`).

Typed writes skip the extractor:

```python
mem.set(user_id="u1", predicate="lives_in", value="Bangalore")
print(mem.state(user_id="u1").values)
print(mem.history(user_id="u1", predicate="lives_in").facts)
```

Look at a file from the shell:

```bash
tensemem inspect --user u1
tensemem history --user u1 lives_in
tensemem search --user u1 "where did I live"
```

Default database is `./tensemem.db`. Pass `--db path.db` to point at another file.

An MCP host can use the same file:

```bash
pip install "tensemem[mcp]"
tensemem mcp --db /absolute/path/tensemem.db --user u1
```

See [MCP](mcp.md) for the tool list and host config.
