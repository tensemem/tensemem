# 0009. TenseBench scores safe-to-act-on properties

- Status: Accepted
- Date: 2026-10-19

## Context

Extraction quality (precision and recall on labeled utterances) does not tell an agent whether it can book travel or change an order. The dangerous failures are stale current-state, silent lag, self-echo, and corrections that come back after a rebuild. Those need a published scoring method that anyone can rerun.

A large hosted-model suite is out of reach for this slice: CI must stay deterministic and offline.

## Decision

1. **TenseBench is an engine benchmark**, not a replacement for the golden extract set. Scenarios are multi-turn conversations with expected ACTIVE triples, stale values, optional echo, correction, rebuild, and read-after-write probes.
2. **CI uses `FakeExtractor`.** Utterances the fake model cannot parse carry scripted ops in the JSONL. Empty `ops` means "extract nothing".
3. **Metrics are the safe-to-act-on set:** current-state accuracy, stale-fact leak rate, freshness honesty, contamination rate, correction durability, history accuracy, and tokens per answer. Denominators skip scenarios that do not exercise the metric; those rates are `n/a`, not 0 or 1.
4. **Baselines in-repo are concatenative history and token-overlap episode retrieval.** They have no freshness flag (honesty 0 on probes) and no extract/correction loop (those rates are omitted). Product names stay out of the harness and docs.
5. **The runner is `tensemem bench`** (also `python -m tensemem.eval bench`) so the method is as public as the numbers.

## Alternatives considered

- **Only grow the golden set.** That scores extract ops, not whether context still shows a superseded city as current.
- **Require a live model in CI.** Flaky, paid, and blocked on keys; the engine properties would not run on every PR.
- **Ship third-party memory adapters in this PR.** That is a later slice; the floor baselines already show leak and honesty without extra dependencies.

## Consequences

- A passing CI run means the engine, guard, and resolver behave on the packaged set, not that a hosted extractor is production-ready.
- Scripted ops can hide extract mistakes; those remain the golden set's job.
- Growing to hundreds of scenarios should keep the same metric definitions so old numbers stay comparable.

## Revisit when

The scenario count crosses a few hundred, hosted-model scoring lands in CI, or we add adapters for other memory APIs.
