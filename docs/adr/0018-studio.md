# 0018. Studio is a Next.js client over Memory

- Status: Accepted
- Date: 2026-10-20

## Context

Operators need to see whether memory is safe to act on. A list of snippets is not enough. The engine already has freshness, history, explain, search, and correct().

## Decision

1. **TenseMem Studio is a Next.js app** in `studio/`. It talks to `tensemem serve` over `/v1`. It is not a second memory API.
2. **Edit is `correct()` / deny / replacement.** The dashboard does not SET slots by key.
3. **Insights (compare, echo, act-risk) are computed in Python** and returned as JSON. The UI only renders them.

## Alternatives considered

- **Static HTML inside the wheel.** Faster to ship, weaker product.
- **Free-text rewrite of a fact.** Skips `resolve()`.

## Consequences

- Two processes locally: serve on 8080, Studio on 3000 with a `/v1` rewrite.
- Hosted multi-tenant Studio stays later.

## Revisit when

We embed Studio in the wheel, or add as-of time travel.
