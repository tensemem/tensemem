# What

- Add Hypothesis as a dev dependency and a `tests/property/` suite for the engine invariants: one ACTIVE fact per slot, commutative independent predicates, `rebuild()` of explicit ops, `forget()` erasure, monotonic watermarks, correction restore + rebuild, fenced echo, acyclic supersession chains.
- CI uses 40 examples per test (`HYPOTHESIS_PROFILE=dev` for a longer local run). Ignore `.hypothesis/`.

# Why

Those invariants were specified as a property-test layer and only covered by a few hand-written cases. Random sequences catch slot, watermark, and correction mistakes that example tests miss.
