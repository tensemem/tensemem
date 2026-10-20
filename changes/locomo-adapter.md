# What

- Add `tensemem locomo` / `python -m tensemem.eval locomo`: load a LoCoMo-shaped JSON array or JSONL, ingest each conversation once, score `context()` against every QA row, and print the five official category IDs.
- Official adversarial rows are unscored unless `abstain_trap` is set. Session stamps keep their time; unknown dates are omitted.
- Ship a one-conversation packaged pilot (GST, itinerary). Optional `ops` on turns keep CI on `FakeExtractor`. Both speakers are extracted.

# Why

Phase 5 asked for both published long-session packs through the same engine. The ten-conversation download and a hosted extractor stay out of CI.
