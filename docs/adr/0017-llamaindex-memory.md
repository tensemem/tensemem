# 0017. LlamaIndex chat memory is an adapter, not a second memory API

- Status: Accepted
- Date: 2026-10-20

## Context

Chat stacks call put/get on a memory object. The engine already has `add` and `context()`. The wrapper must not SET slots by key (ADR 0002).

## Decision

1. **`TenseMemChatMemory` maps `put` → `add()` and `get` → `context()`.** Async `aput` / `aget` call the sync methods.
2. **The adapter does not import the framework.** `tensemem[llamaindex]` only installs both packages together. CI scores the mapping without that extra.

## Alternatives considered

- **Subclass the framework memory ABC.** Ties CI to a moving extra.
- **`put` writes a predicate named by the caller.** Rejected in ADR 0002.

## Consequences

- Empty text is rejected. First-person extract still attaches to `user`.

## Revisit when

We subclass a framework ABC, or add a hosted extractor inside the adapter.
