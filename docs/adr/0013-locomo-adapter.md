# 0013. LoCoMo packs reuse the same context() scorer

- Status: Accepted
- Date: 2026-10-20

## Context

ADR 0012 loads LongMemEval-shaped haystacks (one question per instance). The other published long-session pack is one conversation shared by many questions, with two named speakers and integer category IDs. CI cannot fetch that release or call a hosted extractor.

## Decision

1. **`tensemem locomo` loads the published JSON array** (or JSONL) and scores `context()` against each gold answer. One conversation is ingested once; every QA row reads that store.
2. **Both speakers' turns are extracted.** They are two people, not an assistant restating fenced memory (ADR 0007). Photo-only turns fall back to `blip_caption`.
3. **Category IDs follow the published evaluation script:** 1 multi-hop, 2 temporal, 3 open-domain, 4 single-hop, 5 adversarial. Temporal rows set `include_history=True`.
4. **CI uses a packaged one-conversation pilot** with optional `ops` on turns. The ten-conversation file is `--path` only.
5. **Substring match is the score**, not official F1. Category 5 is scored only when `abstain_trap` is set. Category 3 uses the text before the first `;`. Category 1 requires every comma-separated part.

## Alternatives considered

- **Convert the pack into TenseBench JSONL or LongMemEval haystacks.** Loses official field names and the one-store-per-conversation shape.
- **Require a live model in CI.** Same rejection as ADR 0009 / 0012.

## Consequences

- A passing CI run means the loader, speaker replay, and category report work on the pilot, not that a hosted extractor scored the public ten conversations.
- Downloading the official pack and running this command does not produce official LoCoMo numbers.
- First-person utterances in a downloaded pack attach to `user` unless a later extractor sets the speaker as `subject`.

## Revisit when

We add a hosted-model run of the full pack, session-level recall metrics, or a third long-conversation format.
