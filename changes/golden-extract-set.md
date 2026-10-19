# What

- Grow the labeled extract set to 150+ utterances covering moves, only/also/no longer, retract, deny, hedges, third parties, jobs, diet, tools, and relative dates.
- Teach `FakeExtractor` those patterns so CI still scores precision/recall at 1.0 on the rule-based subset. Confirmations and sarcasm stay `skip_fake` for live models.
- Harden runtime redaction (no comment allowlists; full GitHub tokens and private-key blocks), linear fence stripping, read-only SQLite URI mode, pinned packing and REPLACE_SET in linear time, extractor-proposed aliases that stay off the global registry, and a bounded evidence guard.

# Why

Extraction quality is the bottleneck for a trustworthy v0.1. Eighteen cases could not catch modality, third-party subjects, or retract/deny mistakes. The larger set is the yardstick for prompt and provider changes. The same slice closes the scanner findings on scrub, fences, read-only opens, and shared-registry alias writes.
