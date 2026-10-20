# Long-session eval

`tensemem longmem` loads a [LongMemEval](https://github.com/xiaowu0162/LongMemEval)-shaped JSON pack and scores whether `context()` contains the gold answer. It does not download the 500-item release. The packaged pilot (`src/tensemem/eval/longmem_pilot.json`) is seven short GST / itinerary / inbox conversations so CI stays offline.

```bash
tensemem longmem
python -m tensemem.eval longmem --path /absolute/path/longmemeval_s.json
```

`--path` accepts the official JSON array or JSONL (one instance per line). `--db` is unused; this command does not open a database.

## What is scored

User turns are replayed with `add(..., wait=True)`. Assistant turns are stored in the file but not extracted (ADR 0007). The question is asked through `context()`; temporal-reasoning items set `include_history=True`.

| Bucket | Pass when |
|---|---|
| The six published `question_type` values | The gold `answer` appears in `context().text` |
| Abstention (`question_id` ends in `_abs`) | The gold `answer` is **absent** from the current-fact section |

The report prints accuracy overall, per type, and tokens per answer. Types missing from the file print as `n/a`.

Official instances have no extract labels. The pilot adds optional `ops` on user turns so `FakeExtractor` can apply them. A hosted-model run of the full pack is a later slice.

Session dates (`haystack_dates`) are passed to `add(occurred_at=…)` when they parse.
