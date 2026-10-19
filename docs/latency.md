# Context latency

Empty-query `context()` is the read path an agent uses on every turn: load ACTIVE facts, score, pack, render. It must not call a model.

Laptop target (design §6.2), 5k ACTIVE facts, no query embedding:

| Percentile | Target |
|---|---|
| p50 | ≤ 2 ms |
| p99 | ≤ 10 ms |

```bash
tensemem latency
python -m tensemem.eval latency
tensemem latency --facts 5000 --rounds 80
```

CI runs a smaller seed (500 facts) and fails if p99 ≥ 250 ms. That bound is well above shared-runner noise (p99 of 20 samples is nearly the max) and still catches quadratic packing. The 2 ms / 10 ms numbers are for a laptop-class machine, not GitHub Actions.
