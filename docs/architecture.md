# Architecture

Every surface is an adapter over `Memory` / `AsyncMemory`. The model proposes typed ops; deterministic code applies them. Facts are a rebuildable projection of an append-only episode log (ADR 0001, ADR 0002).

![TenseMem architecture](architecture.svg)

Editable source: [architecture.excalidraw](architecture.excalidraw). Open it in [Excalidraw](https://excalidraw.com) or the VS Code extension, then export SVG over `architecture.svg` in the same folder.

## Paths

**Write.** `add()` stores an episode and an EXTRACT job in one transaction. `set()` / `add_value()` / `retract()` store an `explicit_op` episode and go through the same `resolve()`. `correct()` is DENY when no replacement is given and SET when one is; it restores the displaced value and survives `rebuild()`. `forget()` is the only log delete (a tombstone).

**Extract.** `pipeline/worker.py` leases jobs (`QUEUED` → `LEASED` → `DONE` / `DEAD`). Consecutive due jobs in one scope share one provider call. Order: strip the contamination fence, scrub secrets, `extract()`, `keep_ops` (evidence must be a verbatim quote of user text), `normalize_ops` (unknown predicates drop unless `new_predicate` is set), `apply_policy`, `resolve()`, `apply()` in one write transaction.

**Read.** `state()`, `history()`, `context()`, and `search()` all carry freshness (`as_of_seq`, `pending`, `is_current`). `context()` is fenced on the way out and stripped on the way back in. Default retrieval is FTS; embeddings are optional.

**Store.** One SQLite file, WAL, single writer (`storage/sqlite/`). `StorageBackend` is the lifecycle protocol, not a second SQL dialect (ADR 0020). A `ONE` slot has at most one `ACTIVE` fact (resolver plus a partial unique index).

## Where to change things

| If you are changing… | Start here | Tests |
|---|---|---|
| Ingest, wait, rebuild, correct | `src/tensemem/memory.py` | `tests/` around Memory |
| CLI verbs | `src/tensemem/cli/main.py` | `tests/` CLI |
| REST `/v1` | `src/tensemem/server.py` | server tests |
| Studio pages | `studio/app/` (`page.tsx` board, `memories/`, `playground/`, `echo/`, `ops/`) and `studio/lib/api.ts` | manual Studio + serve |
| MCP tools | `src/tensemem/mcp.py` | MCP tests |
| LangGraph / LlamaIndex | `langgraph.py`, `llamaindex.py` | adapter tests |
| Extract prompt | `pipeline/prompts/extract_v1.md` | `tests/pipeline/test_prompt.py` |
| Worker / jobs | `pipeline/worker.py`, `storage/sqlite/jobs.py` | pipeline + job tests |
| Quote guard | `pipeline/guard.py`, `security/fence.py` | contamination tests |
| Name / cardinality | `pipeline/normalize.py`, `storage/sqlite/registry.py` | normalizer tests |
| Hedges and dates | `pipeline/policy.py` | policy tests |
| Decision table | `core/resolver.py` (pure, no I/O) | `tests/core/`, `tests/property/` |
| Apply + explain | `storage/sqlite/facts.py` | apply / explain tests |
| New LLM | `providers/llm/` — env key, not Studio Token | provider tests; no network in default pytest |
| New embedder | `providers/embed/` | embed tests |
| Schema / migrations | `storage/sqlite/migrate.py` and packaged SQL | migration tests |
| Freshness | `storage/sqlite/snapshot.py`, `storage/sqlite/reads.py` | freshness tests |
| Eval packs | `src/tensemem/eval/` | `tensemem bench` (offline) |

Default pytest never calls a hosted model. A repo admin comments `/test` to run live extract on the default branch only.

## Invariants

- `resolve()` does not touch the database. `apply()` writes.
- Unknown predicates are not auto-registered from free text.
- Extracted ops without a verbatim user-text quote are dropped.
- Recalled `context()` must not be learned as new evidence.
- `correct()` rejected claims survive `rebuild()`.
- At most one `ACTIVE` fact per `ONE` slot.

Decisions live in [ADRs](adr/README.md). Setup and review gates: [CONTRIBUTING.md](../CONTRIBUTING.md).
