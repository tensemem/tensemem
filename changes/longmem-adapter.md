# What

- Add `tensemem longmem` / `python -m tensemem.eval longmem`: load a LongMemEval-shaped JSON array or JSONL, replay user turns, score `context()` against each gold answer, and print every official `question_type` plus abstention.
- Official `_abs` items are unscored unless `abstain_trap` is set. Session stamps keep their time; unknown dates are omitted.
- Ship a 7-item packaged pilot (GST, itinerary, inbox). Optional `ops` on user turns keep CI on `FakeExtractor`. Assistant turns are not extracted.

# Why

A published long-session pack should run through the same engine as TenseBench. The 500-item download and a hosted extractor stay out of CI.
