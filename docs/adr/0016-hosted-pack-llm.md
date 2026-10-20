# 0016. Hosted pack scoring stays out of CI

- Status: Accepted
- Date: 2026-10-20

## Context

ADR 0012 / 0013 load published long-session packs through `FakeExtractor`. Official files have no `ops`. A hosted extractor is the only way to score a downloaded pack, but CI must stay offline and deterministic.

## Decision

1. **`run_longmem` / `run_locomo` take optional `llm=`.** Default is still `FakeExtractor` plus scripted `ops`.
2. **`--llm openai|anthropic|ollama|litellm`** builds that provider. `--llm fake` or omitting the flag keeps CI behavior.
3. **CI never passes `--llm`.** A hosted run is a local or nightly command against a downloaded `--path`.

## Alternatives considered

- **Put official packs and keys in CI.** Same rejection as ADR 0009.
- **A second scoring binary.** One command with an optional flag is enough.

## Consequences

- Passing CI does not mean a hosted extractor scored the public 500 or the ten conversations.
- Substring match is still not official pack accuracy.

## Revisit when

A nightly workflow publishes hosted numbers, or we add a judge model.
