# What

- Add `OllamaProvider` and `LiteLLMProvider` behind optional extras `tensemem[ollama]` and `tensemem[litellm]`.
- Default pytest still injects fakes; neither extra is required to install or test the engine.

# Why

Extract should talk to local models and to a router without each caller building an OpenAI-compatible client by hand.
