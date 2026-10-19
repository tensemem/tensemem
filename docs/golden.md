# Golden extract set

The golden set scores **extraction**, not whether recalled context is safe to act on. That second question is [TenseBench](tensebench.md).

Cases live in `tests/golden/v1.jsonl` (one JSON object per line). Each row is an utterance, the typed ops it should produce, and an optional extract snapshot (`facts`, `registry`). CI scores `FakeExtractor` on every case except `"skip_fake": true` (confirmations and sarcasm, which need a real model).

```bash
python -m tensemem.eval
python -m tensemem.eval --all   # include skip_fake rows
```

`skip_fake` rows are still labeled. They are for live provider runs (`TENSEMEM_LIVE=1`), not for the rule-based extractor.
