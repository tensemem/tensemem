# What

- FTS5 search over facts and episodes, with `Memory.search()` and query-aware `context()` packing so the matching slot wins over recency.
- Optional embeddings (`embedder=`, `tensemem[local]` / OpenAI) via background `embed` jobs; cosine is brute-force within a scope.
- Temporal questions and `include_history=True` include superseded values; weak fact matches fall back to episode snippets.
- `ContextResult.debug` scores, plus `json` / `xml` renderers.

# Why

`context()` still packed the newest ACTIVE facts. A query like "where did I live" must retrieve that slot (and history when asked), not whatever was written last.
