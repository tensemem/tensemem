# What

- CLI (`tensemem inspect|history|explain|search|jobs|freshness|correct|export|import|rebuild|backup|stats`) on the existing Memory API, via argparse (no extra default dependencies).
- `Memory.backup()`, `export_jsonl` / `import_jsonl`, `rebuild()`, `stats()`, structured `tensemem` logs, and `hooks=` / `on()`.
- Concurrency stress (8 threads, two handles on one file) and a v2 migration fixture that applies remaining SQL on open.
- Docs site: quickstart, concepts, API, CLI, operations (including Litestream).

# Why

Developers needed a way to look at state and history, copy a database, and replay the episode log after extractor changes, without waiting for a hosted inspector.
