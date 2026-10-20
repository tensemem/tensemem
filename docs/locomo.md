# LoCoMo eval

`tensemem locomo` loads a [LoCoMo](https://github.com/snap-research/locomo)-shaped JSON pack and scores whether `context()` contains the gold answer. It does not download `data/locomo10.json`. The packaged pilot (`src/tensemem/eval/locomo_pilot.json`) is one short GST / itinerary conversation so CI stays offline.

```bash
tensemem locomo
python -m tensemem.eval locomo --path /absolute/path/locomo10.json
tensemem locomo --path /absolute/path/locomo10.json --llm openai
```

`--path` accepts the official JSON array or JSONL (one conversation per line). `--db` is unused; this command does not open a database. `--llm openai|anthropic|ollama|litellm` uses that extractor (needs the matching extra and its key). Omit `--llm` or pass `--llm fake` to keep `FakeExtractor`. CI never passes `--llm`.

## What is scored

One conversation is ingested once. Both speakers' turns are replayed with `add(..., wait=True)` — they are two people talking, not an assistant echo (ADR 0007). Photo-only turns use `blip_caption` when `text` is empty. Every QA row then asks `context()` against that store. Temporal items (`category` 2) set `include_history=True`.

Category IDs follow the published evaluation script, not the paper's numbered list:

| ID | Bucket | Pass when |
|---|---|---|
| 4 | Single-hop | The gold `answer` appears as a substring in `context().text` |
| 1 | Multi-hop | Every comma-separated part of `answer` appears |
| 2 | Temporal | The gold `answer` appears (`include_history=True`) |
| 3 | Open-domain | The text before the first `;` appears |
| 5 | Adversarial | Optional `abstain_trap` is **absent** from the current-fact section |

Official category-5 `answer` text is a prose explanation. That sentence is not a trap token, so those items are **unscored** unless the pack sets `abstain_trap`. They do not change `ok` or the scored count. Numeric answers (`2022`) are read as strings.

The report is a substring check, not official LoCoMo F1. Full-sentence gold answers in a downloaded pack will usually miss. Categories missing from the file, and unscored adversarial rows, print as `n/a`.

Official instances have no extract labels. The pilot adds optional `ops` on turns so `FakeExtractor` can apply them; omitted `subject` uses the turn's `speaker`. A hosted extractor on a downloaded pack is `--llm` (ADR 0016).

Session stamps (`9:00 am on 1 June, 2026`) keep their time. Stamps that do not parse are omitted (`occurred_at` stays unset) instead of sharing one fallback clock.
