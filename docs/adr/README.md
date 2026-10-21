# Architecture Decision Records

Each record captures one significant design decision: the context, what we chose, what we rejected, and when we should revisit it. Records are immutable once accepted; to change a decision, add a new record that supersedes the old one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-event-sourced-episodes.md) | Raw messages are an append-only log; facts are a rebuildable projection | Accepted |
| [0002](0002-llm-proposes-engine-decides.md) | The LLM proposes typed operations; deterministic code applies them | Accepted |
| [0003](0003-sqlite-single-writer.md) | SQLite is the default store, with one writer per process | Accepted |
| [0004](0004-optional-embeddings.md) | Embeddings are optional; full-text search is the default retrieval path | Accepted |
| [0005](0005-bitemporal-facts.md) | Facts track both valid time and recorded time | Accepted |
| [0006](0006-versioned-freshness-aware-reads.md) | Every read reports how fresh it is | Accepted |
| [0007](0007-self-contamination-guard.md) | Memory never learns from its own output | Accepted |
| [0008](0008-corrections-are-first-class.md) | Corrections are first-class and survive rebuilds | Accepted |
| [0009](0009-tensebench-safe-to-act.md) | TenseBench scores safe-to-act-on properties | Accepted |
| [0010](0010-mcp-stdio.md) | MCP is a stdio adapter over the same engine | Accepted |
| [0011](0011-rest-serve.md) | REST is an HTTP adapter over the same engine | Accepted |
| [0012](0012-longmem-adapter.md) | Long-session packs reuse the engine, not a second memory API | Accepted |
| [0013](0013-locomo-adapter.md) | LoCoMo packs reuse the same context() scorer | Accepted |
| [0014](0014-langgraph-store.md) | The LangGraph store is an adapter, not a second memory API | Accepted |
| [0015](0015-streamable-http-auth.md) | Streamable HTTP MCP and optional bearer auth | Accepted |
| [0016](0016-hosted-pack-llm.md) | Hosted pack scoring stays out of CI | Accepted |
| [0017](0017-llamaindex-memory.md) | LlamaIndex chat memory is an adapter, not a second memory API | Accepted |
| [0018](0018-studio.md) | Studio is a Next.js client over Memory | Accepted |
| [0019](0019-studio-ops.md) | Studio ops chrome uses hashed keys and persisted provider names | Accepted |
| [0020](0020-storage-backend.md) | StorageBackend is the store lifecycle, not a SQL dialect | Accepted |

## Template

```markdown
# NNNN. Title

- Status: Proposed | Accepted | Superseded by NNNN
- Date: YYYY-MM-DD

## Context
## Decision
## Alternatives considered
## Consequences
## Revisit when
```
