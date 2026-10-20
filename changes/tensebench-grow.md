# What

- Grow the packaged TenseBench set from 30 to 70 hand-written conversations. New families cover city and tool aliases, hedges, late backfills (`valid_from` on scripted ops), third-party subjects that must not overwrite the user, job/diet flip-flops, and more echo / freshness / correction probes.
- Same metrics, same `FakeExtractor` CI path, same concat and token-overlap floors.

# Why

The 30-scenario pilot was enough to wire the harness. Safe-to-act-on claims need more of the conversations that ranking memory gets wrong: an older city must not become current, "I might move" must not replace Delhi, and "my wife lives in Mumbai" must not move the user.
