# 0010. MCP is a stdio adapter over the same engine

- Status: Accepted
- Date: 2026-10-19

## Context

Hosts that speak MCP can attach a local process over stdin/stdout and call tools. That is how many desktop agents get persistent memory without embedding a Python library. The engine already has a typed API (`add`, `context`, `state`, `history`, `forget`). The question is how thin the adapter should be, and whether it may edit slots directly.

## Decision

1. **`tensemem mcp` is a stdio server** on the same SQLite file as the CLI (`--db`, default `tensemem.db`). It creates the file if missing. HTTP MCP and REST (`tensemem serve`) are later slices.
2. **Five tools, mapped 1:1 onto the engine:** `remember` → `add()`, `recall_context` → `context()`, `get_state` → `state()`, `get_history` → `history()`, `forget` → `forget()`. Tools return JSON text, including `freshness.is_current` on reads.
3. **The agent does not decide SET/UPDATE.** `remember` only ingests user text. Extraction and `resolve()` still apply typed ops (ADR 0002). There is no tool that writes a predicate by name.
4. **The SDK is an optional extra** (`tensemem[mcp]`). Tool dispatch is independent of that import so CI can score the mapping without the SDK. Missing extra is a clear error, not a partial server.
5. **Default extractor is `FakeExtractor`**, so a desktop config works without an API key. The background worker stays off so jobs already queued in a shared file are not claimed at startup. `remember` waits in the tool call so that message still extracts.
6. **MCP seeds a small starter registry** (the FakeExtractor predicates: `lives_in`, `uses_language`, …). The Python API still starts empty; this seed is only so a fresh `--db` file can extract on the first `remember`.

## Alternatives considered

- **REST only.** Better for multiple processes, but it is a different slice and does not help a local MCP host that expects stdio.
- **Homemade JSON-RPC.** Avoids the extra, but framing and spec drift are easy to get wrong.
- **Tools that SET/ADD/REMOVE slots.** Faster for a model that already knows the predicate, but it reopens the "agent edits memory" path rejected in ADR 0002.

## Consequences

- One SQLite writer per MCP process (ADR 0003). A second process on the same file (CLI inspect, another MCP) serializes on `BEGIN IMMEDIATE`.
- `forget` is irreversible from the tool surface; the host must pass `user_id` (or `--user` as the default).
- Hosted extractors stay out of this process. Swap `llm=` later without changing the tool names.

## Revisit when

We add Streamable HTTP MCP, `tensemem serve`, or a need for a real-model extractor in the MCP process.
