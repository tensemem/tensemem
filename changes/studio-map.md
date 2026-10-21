# What

- Map lists every fact across all lanes in a table (lane, subject, object, status, times).
- Replace the 6-column circle grid with a layered subject → fact → object graph: hover neighborhood, click inspector, drag nodes, pan, zoom, and toggles for predicate links / SUPERSEDES / ACTIVE-only.
- Show job status `LEASED` as In progress. Board jobs are a table. Add and Run path show a loading state, then a notice to watch the Board jobs table. Playground chips are gone; autocomplete uses past queries.
- Studio Add / Run path send `wait: false` so the button releases when the extract job is queued, not when hosted extract finishes. HTTP `POST /v1/memories:add` now defaults to queue-only (`wait: true` still drains). MCP `remember` still waits unless `wait` is set.
- Ops is one extractor field plus optional search ranking. Access tokens are collapsed; they are not required for a local loopback session.

# Why

Lane chips were hard to scan, and the graph looked like a sketch. Operators need was-vs-is in a table and SUPERSEDES on the drawing. Add that waits for hosted extract looks hung; two equal provider dropdowns and an always-open Keys card hid the one choice that matters.
