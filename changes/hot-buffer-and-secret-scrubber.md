# What

- `context()` includes a hot buffer of unprocessed user messages so the agent can see what was just said before extract finishes.
- Incoming episode text is scrubbed of high-confidence secrets (API keys, password assignments, cards, SSNs) before storage and before the model call.

# Why

Read-your-writes should not wait on the extractor, and secrets in chat should not land in SQLite or leave the process toward a provider.
