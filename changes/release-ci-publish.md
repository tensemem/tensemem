# What

- CI path filter: Python jobs (lint, matrix tests, build) run only when `src/`, `tests/`, package metadata, or CI/publish workflows change; Studio jobs run only when `studio/` (or CI) changes. Pushes to `main` still run both. The required **CI** check stays green when a path is skipped.
- Studio CI: `npm ci`, `tsc --noEmit`, and `next build` on Node 22.
- Tag-triggered Publish workflow uploads to PyPI with trusted publishing (OIDC, environment `pypi`). No stored PyPI token. Tag `vX.Y.Z` must match `__version__`.
- Add `CHANGELOG.md` for 0.1.0 with the HTTP `wait` default called out as breaking.

# Why

`pip install tensemem` still served 0.0.1. Studio had no CI. Full OS/Python matrix on every docs-only PR wasted runners and blocked merges when macOS queues timed out.
