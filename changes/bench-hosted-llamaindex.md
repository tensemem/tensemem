# What

- Grow TenseBench from 82 to 101 with 19 paragraph cases (payroll, lease, insurance, visa, Slack, GST, itinerary, invoice, standup, vendor SLA). Always scripted `ops`. No Delhi / Bangalore / "I live in" / "I write Python" in the new turns.
- Add optional `--llm` on `tensemem longmem` / `tensemem locomo` for a hosted extractor. Default and CI stay on `FakeExtractor`.
- Add `TenseMemChatMemory` (`tensemem[llamaindex]`): `put` / `get` over `add()` and `context()`.

# Why

The remaining Phase 5 leftovers were a larger safe-to-act pack, a way to score a downloaded official file without putting keys in CI, and one more framework extra.
