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

`FakeExtractor` is rule-based and needs no API key. Copy is in `examples/quickstart.py`. For a real model, pass any `LLMProvider` (`tensemem[openai]`, `tensemem[anthropic]`, `tensemem[ollama]`, `tensemem[litellm]`) or set `GEMINI_API_KEY` and use the Gemini adapter (`llm` name `gemini`). Do not put a model key in HTTP Token.

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
tensemem --db /absolute/path/tensemem.db mcp --user u1
```

See [MCP](mcp.md) for stdio, Streamable HTTP (`--http`), and the tool list.

HTTP on the same file:

```bash
pip install "tensemem[server]"
tensemem --db /absolute/path/tensemem.db serve --port 8080
```

See [REST](server.md) for the routes.

Local inspector ([Studio](studio.md)) needs a repository checkout (`studio/` is not on PyPI). From the repo root:

```bash
git clone https://github.com/tensemem/tensemem.git
cd tensemem
pip install "tensemem[server]"
```

Terminal 1 — HTTP:

```bash
tensemem --db ./studio.db serve --port 8080
```

Terminal 2 — Studio:

```bash
cd studio && npm install && npm run dev
```

Open `http://127.0.0.1:3000`. Token is optional bearer auth, not a model key.
