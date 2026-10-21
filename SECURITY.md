# Security

Report vulnerabilities through [GitHub security advisories](https://github.com/tensemem/tensemem/security/advisories) on this repository. Do not file a public issue for a live secret or an auth bypass.

## Secrets

- Model keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`) stay in the process environment. They are never valid values for Studio **Token**.
- `TENSEMEM_TOKEN` and issued `tm_…` keys are bearer auth for HTTP, not model keys.
- `add()` redacts common secret shapes with detect-secrets before text is stored or sent to a provider.

## Bind

`tensemem serve` and `tensemem mcp --http` default to loopback and do not terminate TLS. A non-loopback bind needs a TLS-terminating proxy that also authorizes the `user_id` the client sends.
