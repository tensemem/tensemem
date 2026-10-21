# Changelog

All notable changes are listed here. The `changes/` folder holds per-PR notes; this file is the release-facing summary.

## 0.1.0 — 2026-10-21

First alpha on PyPI after `0.0.1`. Install with `pip install tensemem` (or `uv add tensemem`). Studio stays in the git checkout; it is not on PyPI.

### Breaking

- **HTTP `POST /v1/memories:add` returns when the extract job is queued.** It no longer waits for facts to appear in the response. Clients that need extract to finish in that request must send `"wait": true`. MCP `remember` still waits unless `wait` is set. Python `Memory.add(..., wait=False)` is unchanged (default remains false).

### Added

- **TenseMem Studio** — Next.js inspector over `tensemem serve`: safe-to-act board, memories table, playground, stale-act lab, map (lanes table + interactive graph), echo lab, Ops (extractor, search ranking, optional access tokens).
- **REST serve** (`tensemem[server]`) — remember/recall plus inspect and insight routes; optional bearer (`--token` / `TENSEMEM_TOKEN` or issued `tm_…` keys).
- **MCP** (`tensemem[mcp]`) — stdio and Streamable HTTP (`--http`) with `remember`, `recall_context`, `get_state`, `get_history`, `forget`.
- **Extract providers** — OpenAI, Anthropic, Ollama, LiteLLM, Gemini (`GEMINI_API_KEY`); default `FakeExtractor` for CI.
- **Retrieval** — FTS5 search, optional embeddings (`tensemem[local]` / OpenAI), query-aware `context()`, hot buffer of unprocessed messages, secret scrubbing before store and model calls.
- **CLI** — inspect, history, explain, search, jobs, freshness, correct, export/import, rebuild, backup, stats, bench, longmem, locomo, latency, mcp, serve.
- **Adapters** — `TenseMemStore` (`tensemem[langgraph]`), `TenseMemChatMemory` (`tensemem[llamaindex]`).
- **Benchmarks** — TenseBench (101 packaged scenarios), LongMemEval-shaped and LoCoMo-shaped adapters with offline pilots; optional hosted `--llm` for downloaded packs (not in CI).
- **Storage** — `StorageBackend` / `SqliteBackend` seam (`store=` on `Memory`).
- **Docs** — README quickstart, architecture diagram, CONTRIBUTING merge gates, SECURITY.md.

### Changed

- Package version and classifier are **0.1.0 alpha**.
- Studio Add / Run path queue extract and show a job-submitted notice; Board shows `LEASED` as In progress.
- Ops focuses on Extractor + Search ranking; access tokens are optional and collapsed.

### Security

- Model keys stay in the serve process environment, never in Studio Token.
- `add()` redacts common secret shapes with detect-secrets before storage and provider calls.
- Non-loopback bind needs a TLS-terminating proxy that authorizes `user_id`.
