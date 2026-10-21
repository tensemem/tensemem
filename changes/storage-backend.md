# What

- Add a `StorageBackend` protocol for store lifecycle (`now`, `write`, `transaction`, `read`, `seed`, `backup_to`, `close`).
- `Memory` / `AsyncMemory` accept `store=` (default remains on-disk SQLite). An injected store is not closed by `Memory.close()`.
- Conformance tests run that lifecycle against `SqliteDatabase` so a later backend can register the same factory.

# Why

ADR 0003 promised a seam before a second store. The engine constructed `SqliteDatabase` directly, so a later driver would have to edit `Memory` instead of implementing a protocol.
