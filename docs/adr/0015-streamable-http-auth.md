# 0015. Streamable HTTP MCP and optional bearer auth

- Status: Accepted
- Date: 2026-10-20

## Context

ADR 0010 is stdio MCP. ADR 0011 is REST without authentication. Hosts that speak Streamable HTTP, and any non-loopback bind, need a token in this process. TLS termination stays outside.

## Decision

1. **`tensemem mcp --http` is Streamable HTTP** on the same five tools and SQLite file. Default bind is `127.0.0.1:8081`. Stdio remains the default when `--http` is omitted.
2. **Optional bearer token** on REST and Streamable HTTP: `--token` or `TENSEMEM_TOKEN`. When set, requests need `Authorization: Bearer <token>`. `GET /health` on REST stays open. Stdio MCP does not use the token.
3. **No TLS in this process.** A non-loopback bind without a token still warns that auth and TLS are off. A non-loopback bind with a token warns that TLS is still off.
4. **Dispatch stays independent of the extras.** Token checks live in `tensemem.auth` so CI can score them without FastAPI or the MCP SDK.

## Alternatives considered

- **OAuth in-process.** Too much surface for a single shared token.
- **Require a token on loopback.** Breaks the current local CLI default.

## Consequences

- A leaked `--token` on the process list is a credential leak; prefer `TENSEMEM_TOKEN`.
- User-scoped authorization (this token may only read `user_id=u1`) stays in a proxy.

## Revisit when

We add per-user tokens, mTLS, or a real-model extractor in the HTTP process.
