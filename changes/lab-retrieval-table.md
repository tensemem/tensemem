# Show Lab retrieval tester as a table

## What

Replace the single JSON dump in the Lab retrieval tester with:

- Hits rendered as a table (kind, id, text, score, status, predicate).
- Packed context shown in its own block.
- Freshness as a one-line summary.

## Why

The previous large JSON dump was hard to scan. A table makes the ranked hits readable at a glance while keeping the packed context and freshness visible.
