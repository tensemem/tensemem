# Contributing to TenseMem

## Setup

TenseMem uses [uv](https://docs.astral.sh/uv/) for environments and dependencies.

```bash
git clone https://github.com/tensemem/tensemem.git
cd tensemem
uv sync                      # creates .venv with dev tools
uv run pre-commit install    # lint and format on every commit
```

## Checks

CI runs these on every pull request; run them locally before pushing:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uvx codespell --skip="*.lock,.git,uv.lock" --ignore-words-list="tensemem"
```

Default pytest never calls a model. To run the live extract locally after `uv sync --extra openai`:

```bash
TENSEMEM_LIVE=1 uv run pytest -m live
```

Every PR also gets free automated review gates:

| Check | What it does |
|---|---|
| **CI** | Ruff (with inline annotations), format, pyright, pytest, package build |
| **PR quality** | Requires `## What` / `## Why` / `## Docs` in the body; fails oversized diffs (>1000 lines unless labeled `large-pr`); actionlint posts workflow findings as review comments; gitleaks scans for secrets |
| **CodeQL** | Security analysis for Python and GitHub Actions (free on public repos) |
| **Live extract** | Not on every PR. A repository admin comments `/test` on a PR to run `pytest -m live` against a real model on one canonical chat (Delhi, then a move to Bangalore / Rust). It checks out the default branch only, so unmerged PR code never sees `OPENAI_API_KEY`. Test a branch locally with `TENSEMEM_LIVE=1`. |

We do **not** depend on third-party AI review apps (many look free then push a paid trial). Quality comes from the gates above plus human review.

In branch protection, require at least: `Lint and type-check`, `PR description and size`, and `Analyze (python)`.

## Workflow

- `main` is protected. All changes go through pull requests.
- Keep each PR focused on one change, and describe what changed and why. Use the pull request template.
- Significant design changes need an architecture decision record in `docs/adr/`.
- Write commit messages in the imperative mood, for example "Add predicate registry".
- Agents and editors should follow the project rules in [`.cursor/rules/`](.cursor/rules/) (short PRs, docs in the same change, vendor-neutral public docs).
