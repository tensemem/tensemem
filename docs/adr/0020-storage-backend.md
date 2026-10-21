# 0020. StorageBackend is the store lifecycle, not a SQL dialect

- Status: Accepted
- Date: 2026-10-21

## Context

ADR 0003 promised a `StorageBackend` protocol so a second store can pass the same tests. `Memory` still constructed `SqliteDatabase` and `store()` returned that concrete type. A Postgres driver would have to edit the engine, not implement a seam.

## Decision

1. **`StorageBackend` is the lifecycle.** `now`, `write`, `transaction`, `read`, `seed`, `backup_to`, `close`, and a context manager. Work units stay backend-private. SQLite still passes a connection into those callables.
2. **`Memory` and `AsyncMemory` accept `store=`.** When it is set, they do not open a file and they do not close the injected store. `store()` returns the protocol.
3. **Conformance tests** exercise the lifecycle through `Memory` (`set` / `state`, `seed`, `backup_to`, close-after-use). They take a factory so a later backend can register itself. This slice ships the SQLite factory only.
4. **SQL modules stay SQLite.** Jobs, facts, FTS, and ops chrome still import `sqlite3`. A dialect change is a later driver PR.

## Alternatives considered

- **Abstract every repository behind typed methods.** Correct long-term, too large for one PR, and would rewrite working SQL.
- **Generic `StorageBackend[Conn]`.** Forces `Memory` to become generic or to hide the type parameter; callers still pass SQLite-shaped functions.

## Consequences

- A second backend can implement the protocol and join the conformance suite without changing `set()` / `state()`.
- Injected stores outlive `Memory.close()`, so tests and a future server can share one writer.
- Raw SQL in ops and the extract worker still assumes SQLite until that driver lands.

## Revisit when

A second backend exists, or repository methods move onto the protocol so work units no longer carry SQL.
