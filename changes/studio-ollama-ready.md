# What

- Ops' readiness message for the **Ollama (local)** extractor says "Ready — uses local Ollama." instead of "Ready — serve has an env key."
- Other extractors keep their current messages.

# Why

Ollama runs locally and needs no key, so the env-key message was misleading (#51).
