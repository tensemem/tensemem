# Operations

`Memory` talks to a `SqliteBackend` (ADR 0020). The default is `SqliteDatabase`. Pass `store=` to inject another SQLite-shaped store; conformance lives in `tests/storage/test_backend.py`. A different SQL dialect needs repository changes, not only `StorageBackend`.

## Backup

```python
mem.backup("tensemem.bak.db")
```

This uses SQLite's online backup API on the writer connection, so it is consistent with in-flight transactions. The CLI equivalent is `tensemem backup copy.db`.

Opening an existing file that still has pending schema migrations copies it to `*.bak` first, then applies the remaining SQL.

## JSONL export and import

`export_jsonl` writes the predicate registry and that user's episodes. `import_jsonl` replays them as new `register_predicate` / `set` / `add` calls, so public ids change. Corrections are preserved by `backup()` and by `rebuild()` on the original file (rejected claims stay in SQLite).

## Litestream

For a durable single-node file, stream the WAL:

```bash
# Example: replicate tensemem.db to S3-compatible storage.
litestream replicate tensemem.db s3://your-bucket/tensemem
```

SQLite is opened in WAL mode with `synchronous=NORMAL` and `busy_timeout=5000`. Run Litestream beside the process that owns the file. Restore by stopping writers, then:

```bash
# Output path must not already exist.
litestream restore -o tensemem-restored.db s3://your-bucket/tensemem
```

## Migrations

Numbered files live in the package (`0001_init.sql`, …) and run automatically on open. Tests open databases that stopped at an earlier version and check that remaining migrations apply and data is still searchable.

## Concurrency

One writer thread per `Memory` process. Two processes (or two `Memory` handles) on the same file serialize on `BEGIN IMMEDIATE` plus the busy timeout. `tensemem mcp` and `tensemem serve` are each one such process; inspect with the CLI while they run is safe. For heavy multi-process ingest, run one `tensemem serve` writer and talk to it over HTTP.

`tensemem serve` has no authentication and no TLS. Keep the default loopback bind (`127.0.0.1`). If `--host` exposes it on a network, place a TLS-terminating reverse proxy in front that authenticates callers and authorizes the `user_id` they send. Anyone who can reach an unbound server can read or `DELETE` any scope.
