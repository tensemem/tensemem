# What

- Add `tensemem latency` / `python -m tensemem.eval latency`: seed ACTIVE facts, time empty-query `context()`, print p50/p99/max against the 2 ms / 10 ms targets.
- CI runs 500 facts and fails if p99 ≥ 250 ms.

# Why

The engine claims millisecond reads with no LLM on the path. That SLO was undocumented and unmeasured. A small harness plus a generous CI gate makes regressions visible without depending on GitHub Actions wall-clock noise.
