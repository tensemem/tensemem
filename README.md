# TenseMem

**Memory that knows its tenses.** Embedded, deterministic memory that AI agents can safely act on.

> Status: pre-alpha. The deterministic API can set, correct, and read versioned facts. LLM extraction is next.

## The problem

Vector memory has no idea what is current. Tell an agent "I live in Delhi" in January and "I moved to Bangalore" in June, and a similarity search returns both, leaving the model to guess.

Even memory that tracks changes usually can't tell you whether it's up to date, and it tends to re-learn its own output when recalled facts flow back into the conversation. For an agent that books travel, edits code, or changes an order, stale or self-reinforced memory is a bug.

## What TenseMem does

- **One current truth per fact, enforced.** Declare that `lives_in` has a single value, and the engine guarantees it: a new value supersedes the old one, which stays in history for "where did I live before?"
- **Every read says how fresh it is.** Results report which messages they reflect and whether any are still being processed. Ask for a specific message to be applied before you act, or get a clear flag that it hasn't been.
- **Memory never learns from its own echo.** Recalled context is fenced and ignored on the way back in, and every fact needs a verbatim quote from the user.
- **Mistakes can be corrected for good.** Mark a fact wrong and the value it displaced comes back; corrections survive re-extraction with a newer model.
- **The LLM proposes, the engine decides.** The model turns text into typed operations; deterministic, tested rules decide how state changes.
- **No infrastructure.** A single SQLite file inside your process.

## API (deterministic, no LLM yet)

```python
from tensemem import Memory

mem = Memory()
mem.register_predicate("lives_in")
mem.set(user_id="u1", predicate="lives_in", value="Delhi")
mem.set(user_id="u1", predicate="lives_in", value="Bangalore")

mem.state(user_id="u1").values  # {"lives_in": "Bangalore"}
mem.history(user_id="u1", predicate="lives_in")
mem.correct(wrong_fact_id)  # restores the value it displaced
```

`mem.add(...)` / `mem.context(...)` come with the extraction pipeline.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and workflow, and [docs/adr](docs/adr) for the design decisions behind the engine.

## License

[Apache-2.0](LICENSE)
