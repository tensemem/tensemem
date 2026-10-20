# TenseMem

**Memory that knows its tenses.** Embedded, deterministic memory that AI agents can safely act on.

TenseMem stores raw messages as an append-only log and projects them into facts with enforced cardinality, valid time, and a freshness watermark on every read. Recalled context is fenced so the engine does not learn from its own output. Corrections restore displaced values and survive a rebuild.

## Start here

- [Quickstart](quickstart.md) — three lines to a fenced `context()` block
- [Concepts](concepts.md) — episodes, facts, freshness, fences, corrections
- [Python API](api.md) — `Memory` and `AsyncMemory`
- [CLI](cli.md) — inspect, history, explain, search, jobs, bench, longmem, latency, mcp, serve
- [MCP](mcp.md) — stdio tools for remember / recall / state / history / forget
- [REST](server.md) — HTTP routes for add / context / state / history / forget
- [TenseBench](tensebench.md) — safe-to-act-on metrics
- [Long-session eval](longmem.md) — LongMemEval-shaped packs scored through `context()`
- [Golden extract](golden.md) — labeled utterances for precision and recall
- [Context latency](latency.md) — empty-query `context()` percentiles
- [Operations](ops.md) — backup, JSONL export, Litestream, migrations

Local preview (optional): `uvx mkdocs serve`.
