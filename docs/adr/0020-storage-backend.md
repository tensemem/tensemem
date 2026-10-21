# 0020. StorageBackend is the store lifecycle, not a SQL dialect

- Status: Accepted
- Date: 2026-10-21

## Context

ADR 0003 promised a `StorageBackend` protocol so a second store can pass the same tests. `Memory` still constructed `SqliteDatabase` and `store()` returned that concrete type. A Postgres driver would have to edit the engine, not implement a seam.

## Decision

1. **`StorageBackend` is the lifecycle.** `now`, `write`, `transaction`, `read`, `seed`, `backup_to`, `close`, and a context manager. Work-unit type is backend-private.
2. **`SqliteBackend` is the engine contract.** Work units are `sqlite3.Connection`. `Memory` / `AsyncMemory` `store=` and the extract worker accept this, not an arbitrary `StorageBackend`. They do not close an injected store.
3. **Conformance tests** exercise the lifecycle through `Memory` (`set` / `state`, `seed`, `backup_to`, close-after-use). They take a factory. This slice ships the SQLite factory only.
4. **SQL modules stay SQLite.** Jobs, facts, FTS, ops chrome, and `SqliteCache` still import `sqlite3`. A different dialect needs those repositories rewritten; implementing `StorageBackend` alone is not enough.

## Alternatives considered

- **Abstract every repository behind typed methods.** Correct long-term, too large for one PR, and would rewrite working SQL.
- **Generic `StorageBackend[Conn]`.** Forces `Memory` to become generic or to hide the type parameter; callers still pass SQLite-shaped functions.

## Consequences

- `set()` / `state()` stay unchanged only for a `SqliteBackend`. Another SQL dialect needs repository changes, not just the lifecycle protocol.
- Injected stores outlive `Memory.close()`, so tests and a future server can share one writer.
- A later driver registers a factory in the conformance suite after its repositories exist.

## Revisit when

A second backend exists, or repository methods move onto the protocol so work units no longer carry SQL.
