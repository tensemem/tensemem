# What

- TenseBench v1 pilot: 30 JSONL scenarios, a scoring harness, and `tensemem bench` / `python -m tensemem.eval bench`.
- Metrics: current-state accuracy, stale-fact leak rate, freshness honesty, contamination rate, correction durability, history accuracy, tokens per answer. CI uses `FakeExtractor`. Concat and token-overlap baselines ship beside TenseMem.

# Why

Agents need a reproducible answer to "is this memory safe to act on?", not only extract precision. The pilot is small enough to run on every PR and large enough to cover moves, only/also/no longer, aliases, corrections, echo, and read-after-write.
