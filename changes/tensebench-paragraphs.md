# What

- Add 12 TenseBench `paragraph` scenarios: one user message states several predicates at once (GST filing, itinerary, email/invoice routing).
- Turns are scripted so CI stays on `FakeExtractor`. Updates, hedges, a third-party CA, and an echo probe use the same metrics as the rest of the set.

# Why

Agents ingest long notes, not one fact per turn. The packaged set was almost all short live-in / I-write lines, so it did not score whether a filing or travel paragraph keeps one current value per slot.
