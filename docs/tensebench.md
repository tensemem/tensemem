# TenseBench

TenseBench scores whether recalled memory is **safe to act on**. Extraction precision lives in the golden set (`python -m tensemem.eval`). This harness asks a different question: after state changes, does the system still present an outdated fact as if it were current?

The pilot (`src/tensemem/eval/tensebench_v1.jsonl`, shipped in the package) is 30 hand-written conversations. CI runs it with `FakeExtractor` so the numbers are deterministic. A later slice grows the set and adds hosted-model runs.

```bash
tensemem bench
python -m tensemem.eval bench
```

## Metrics

| Metric | What it counts | Pilot target |
|---|---|---|
| Current-state accuracy | Expected ACTIVE triples match exactly | ≥ 0.95 |
| Stale-fact leak rate | Outdated values presented as current (ACTIVE facts, or current-fact bullets). Labeled `(previously …)` text and episode snippets do not count. | 0 |
| Freshness honesty | Reads that have not applied the last message report `is_current=False` | 1.0 |
| Contamination rate | Echoing fenced `context()` changes facts or confidence | 0 |
| Correction durability | A rejected value is absent from history after optional `rebuild()` | 1.0 |
| History accuracy | Version chain for a predicate matches the labeled order | 1.0 |
| Tokens per answer | Mean `context()` tokens (or baseline text tokens) | report only |

A scenario that does not exercise a metric is omitted from that denominator and prints as `n/a`. Freshness cases never wait for extract. Echo cases feed `context().text` back into `add()`. Correction cases call `correct()` (or a scripted `DENY`) and may `rebuild()`.

## Baselines

The same conversations are scored as **concat** (the full user transcript) and **similarity** (the two turns with the most query-token overlap). Neither has a freshness flag, so honesty is 0 on probe cases. They have no extract loop or correction API, so those rates are not scored.

Do not treat concat or similarity as competing products; they exist so the leak and honesty numbers have a published, reproducible floor.

## Adding a scenario

One JSON object per line in `src/tensemem/eval/tensebench_v1.jsonl`. Rule-based `FakeExtractor` handles `I live in …`, `I moved to …`, `I write …`, and `I now only write …`. Other utterances set `"ops"` (including `"ops": []` when the extractor must stay silent). Entity aliases go in `"entities"`.
