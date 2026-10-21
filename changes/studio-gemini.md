# What

- Accept `gemini` as a Studio / serve extractor name. It calls Gemini `generateContent` with `gemini-3.6-flash` (override `TENSEMEM_LITELLM_MODEL`; falls back if a model returns 503).
- `tensemem serve` honors `TENSEMEM_LLM` when applying the persisted provider.
- Hosted `add()` waits up to 60s so a live extract can finish.
- Extract prompt accepts durable facts about any subject (stories, articles, notes), not only first-person identity. Gemini registers unknown predicates and fills missing evidence quotes so those ops are not dropped.
- Studio Memories lists facts in a full-width table (subject / predicate / object / status). Replace is disabled until a replacement value is entered.

# Why

Ops could name OpenAI or LiteLLM, but a Gemini key in the environment had no matching picker and default LiteLLM still targeted OpenAI. An empty Correct was a deny, so facts vanished from the list.
