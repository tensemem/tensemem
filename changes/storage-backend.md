# What

- Add a `StorageBackend` protocol for store lifecycle and a `SqliteBackend` whose work units are `sqlite3.Connection`.
- `Memory` / `AsyncMemory` accept `store=` as a `SqliteBackend` (default remains on-disk SQLite). An injected store is not closed by `Memory.close()`.
- Conformance tests run that lifecycle against `SqliteDatabase` so a later SQLite-shaped backend can register the same factory.

# Why

ADR 0003 promised a seam before a second store. The engine constructed `SqliteDatabase` directly, so a later driver would have to edit `Memory` instead of implementing a protocol.
