# 0019. Studio ops chrome uses hashed keys and persisted provider names

- Status: Accepted
- Date: 2026-10-20

## Context

ADR 0015 is one optional bearer token. A dashboard needs issue/revoke keys, a request log, and a provider picker. Serve still defaults to `FakeExtractor` with the extract worker off.

## Decision

1. **API keys** live in SQLite (`prefix` + PBKDF2 hash). `Authorization: Bearer` accepts `TENSEMEM_TOKEN` or any live key. When any live key exists, anonymous `/v1` calls are rejected. `GET /health` stays open.
2. **Request log** records method, path, status, latency, and key prefix (not the secret).
3. **Provider settings** persist `llm` / `embedder` names. Secrets stay in the environment. Default is fake. Saving a hosted name applies it in-process and starts the extract worker. The worker stays off in the default fake path so queued jobs are not stolen.

## Alternatives considered

- **Bcrypt package.** Stdlib PBKDF2 avoids a new extra.
- **Always start the extract worker.** Would claim jobs meant for another process.

## Consequences

- Hosted extract sends user text to that provider.
- First issued key locks the API until a bearer is presented.

## Revisit when

We start the worker automatically for a hosted provider, or add per-user key scopes.
