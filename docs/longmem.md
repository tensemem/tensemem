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
| The six published `question_type` values | The gold `answer` appears as a substring in `context().text` |
| Abstention (`question_id` ends in `_abs`) | Optional `abstain_trap` is **absent** from the current-fact section |

Official `_abs` items put a prose explanation in `answer`. That sentence is not a trap token, so those items are **unscored** unless the pack sets `abstain_trap`. They do not change `ok` or the scored count.

The report is a substring check, not official LongMemEval accuracy. Full-sentence gold answers in a downloaded pack will usually miss. Types missing from the file, and unscored abstention, print as `n/a`.

Official instances have no extract labels. The pilot adds optional `ops` on user turns so `FakeExtractor` can apply them. A hosted-model run of the full pack is a later slice.

Session dates (`YYYY/MM/DD [(Mon)] [HH:MM]`) keep their time. Stamps that do not parse are omitted (`occurred_at` stays unset) instead of sharing one fallback clock.
