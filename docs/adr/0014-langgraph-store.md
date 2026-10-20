# 0014. The LangGraph store is an adapter, not a second memory API

- Status: Accepted
- Date: 2026-10-20

## Context

Graphs that inject a store call `put` / `search` / `get` / `delete` with a namespace tuple. The engine already has `add` and `context()`. A wrapper must not let the graph SET slots by key (ADR 0002).

## Decision

1. **`TenseMemStore` maps store verbs onto the engine:** `put` → `add()` of `value.text` (or `content` / `memory`), `search` / `get("context")` → `context()`, `get("state")` → `state()`, `delete("scope")` → `forget()`. The store key on `put` is ignored.
2. **`namespace[0]` is `user_id`.** `namespace[1]` is optional `agent_id`. The engine namespace string is set on the store, not the tuple.
3. **The adapter does not import the framework.** `tensemem[langgraph]` is an optional extra so an app can install both packages together. CI scores the mapping without that extra.

## Alternatives considered

- **Subclass the framework store ABC in this package.** Ties CI and types to a moving extra.
- **`put` writes `key` as a predicate.** Reopens the agent-edits-memory path rejected in ADR 0002.

## Consequences

- A graph that `put`s `{"lives_in": "Delhi"}` without a text field is rejected.
- First-person extract still attaches to `user` unless a later extractor sets another subject.

## Revisit when

We add another framework extra, or a hosted extractor inside the store.
