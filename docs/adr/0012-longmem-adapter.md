# 0012. Long-session packs reuse the engine, not a second memory API

- Status: Accepted
- Date: 2026-10-20

## Context

TenseBench is our safe-to-act-on harness. Published long-session packs use a different JSON shape: parallel haystack sessions, a question, a gold answer, and a `question_type`. CI cannot fetch those full packs or call a hosted extractor.

## Decision

1. **`tensemem longmem` loads the published JSON array** (or JSONL) and scores `context()` against each gold answer. The six official `question_type` values are always printed; abstention is `question_id` ending in `_abs`.
2. **Only user turns are extracted.** Assistant turns stay in the file for fidelity with the pack; they are not evidence (ADR 0007).
3. **CI uses a packaged seven-item pilot** with optional `ops` on user turns. The full 500-item file is `--path` only.
4. **Substring match is the score**, not a hosted judge. Official abstention `answer` text is an explanation, so `_abs` items are scored only when `abstain_trap` is set. Temporal-reasoning items set `include_history=True`.

## Alternatives considered

- **Convert packs into TenseBench JSONL.** Loses official field names and makes `--path` to a downloaded file awkward.
- **Require a live model in CI.** Same rejection as ADR 0009.

## Consequences

- A passing CI run means the loader, user-turn replay, and category report work on the pilot, not that a hosted extractor scored the public 500.
- Downloading the official pack and running this command does not produce official LongMemEval numbers.
- Assistant-only evidence in a downloaded pack will miss unless a later user turn confirms it.

## Revisit when

We add a hosted-model run of the full pack, session-level recall metrics, or a second long-conversation pack.
