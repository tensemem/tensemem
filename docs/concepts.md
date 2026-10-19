# Concepts

## Episodes and facts

Every ingest is an **episode**: a user message or an explicit op such as `set()`. Facts are a **projection** of that log. Improve the extractor and call `rebuild()` to replay the same episodes through the current pipeline.

## Cardinality

A `ONE` predicate (`lives_in`) has at most one `ACTIVE` value. A newer value supersedes the old one; the old row stays in `history()` for "where did I live before?". A `MANY` predicate (`uses_language`) keeps several active values until `replace_values` or `remove_value`.

## Freshness

Every read (`state`, `history`, `context`, `search`) includes a watermark: which episode sequence it reflects, how many messages are still pending, and whether any jobs failed. `context(..., min_seq=added.seq, wait=1.5)` waits for that message to be applied, then flags (or raises) if it is still stale.

## Contamination fence

`context()` wraps recalled text in a database-specific fence. On the way back in, fenced spans are stripped before extract, and proposed ops need a verbatim quote from the remaining user text.

## Corrections

`correct(fact_id)` marks a fact as never true, restores the value it displaced, and records a rejected claim. Rebuilds keep those claims, so a newer extractor does not reintroduce the mistake. A later genuine change (a real move) can still be stored, because the claim only blocks episodes at or before the correction.

## FAQ

**Why not store only embeddings?** Similarity search returns both "I live in Delhi" and "I moved to Bangalore" and leaves the model to guess which is current. TenseMem enforces one current value per slot and keeps the rest as dated history.

**Does the model decide what to remember?** It proposes typed operations. Deterministic, tested rules decide how state changes.

**What happens if extract is slow?** `context()` still returns the last known facts plus a hot buffer of unprocessed user messages, and freshness tells you it is not current.
