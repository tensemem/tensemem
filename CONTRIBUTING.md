# Contributing to TenseMem

Read [Architecture](docs/architecture.md) before you pick a file. The picture in the README is the same map: surfaces → `Memory` → write / extract / read → one SQLite file.

## Setup

TenseMem uses [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/tensemem/tensemem.git
cd tensemem
uv sync
uv run pre-commit install
```

Optional extras (same names as on PyPI):

```bash
uv sync --extra server --extra mcp
```

## Checks

Run these from the repo root before you push. CI runs the same set for the paths you touch.

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uvx codespell --skip="*.lock,.git,uv.lock" --ignore-words-list="tensemem"
```

Studio (when you change `studio/`):

```bash
cd studio && npm ci && npm run typecheck && npm run build
```

Default pytest never calls a model. After `uv sync --extra openai`:

```bash
TENSEMEM_LIVE=1 uv run pytest -m live
```

| Check | What it does |
|---|---|
| **CI** | Aggregator. Green when every *needed* job passes; skipped path jobs do not fail the gate |
| **Detect paths** | On pull requests: Python jobs if `src/`, `tests/`, package metadata, or CI/publish workflows change; Studio jobs if `studio/` (or CI) changes. Pushes to `main` run both |
| **Lint and type-check** | Ruff, format, pyright, codespell (Python path) |
| **Test (`os`, Python `x`)** | `pytest` on Ubuntu / macOS / Windows × 3.11–3.15 (Python path) |
| **Build distributions** | `uv build` + `twine check` (Python path) |
| **Studio** | `npm ci`, `tsc --noEmit`, `next build` (Studio path) |
| **PR quality** | Aggregator. Green only when description/size, actionlint, and gitleaks pass |
| **PR description and size** | Requires `## Issue` (with `#N`) / `## What` / `## Why` / `## Docs`; Studio UI PRs also need `## UI` with screenshots/video; fails diffs over 1000 lines unless labeled `large-pr` |
| **CodeQL** | `Analyze (python)` and `Analyze (actions)` |
| **Publish** | Not a merge gate. On `v*` tags, builds the wheel and uploads to PyPI via trusted publishing |
| **Live extract** | Not a merge gate. A repo admin comments `/test` to run `pytest -m live` on the default branch only, so unmerged code never sees hosted keys |

`main` cannot merge while any required check is red or pending. Required checks are **CI**, **PR quality**, **Analyze (python)**, and **Analyze (actions)**. Admins are not exempt. Force-pushes and deleting `main` stay blocked. Live extract and Publish are optional and must stay that way.

## Studio and serve

Two processes, one SQLite file:

```bash
uv sync --extra server
uv run tensemem --db ./studio.db serve --port 8080
# other terminal
cd studio && npm install && npm run dev
```

Hosted extract (Gemini, OpenAI, …) reads keys from **that serve process environment**. Do not paste model keys into Studio Token. Token is `TENSEMEM_TOKEN` or an issued `tm_…` ops key.

Do not commit `*.db`, `*.db-wal`, `*.db-shm`, Studio `node_modules`, or `.next`.

## Picking an issue

Do **not** open a pull request for an open issue until a maintainer has **assigned that issue to you**.

1. Comment on the issue that you want to work on it (one or two sentences is enough).
2. Wait until you are listed as the assignee.
3. Then branch, implement, and open the PR.

If the issue is already assigned to someone else, pick another issue or ask in a comment whether they are still working on it. Unsolicited PRs that skip assignment may be closed so two people do not duplicate the same work. Maintainers may still open unsolicited fix PRs; those titles use `[no-issue]`.

## Pull requests

`main` is protected and cannot merge while required checks are red or pending. One concern per PR.

1. Title includes exactly one of `[low-risk]`, `[medium-risk]`, `[high-risk]`.
2. Body includes an **Issue** section that references the GitHub issue (`Fixes #123` or `Refs #123`). Use `Fixes` when merging should close the issue. Titles may include `[no-issue]` only for maintainer work that has no tracking issue.
3. Add **one** new file `changes/<kebab-slug>.md` (What + Why), unless the title includes `[no-changeset]`.
4. **Studio / UI PRs** (any change under `studio/`): the body must include before/after **screenshots or a short screen recording** in a **UI** section (drag images into the GitHub PR description, or link a video). Pure config/docs under `studio/` with no visible UI change may use `[no-ui]` in the title.
5. Significant design choices get an ADR in `docs/adr/` and a row in `docs/adr/README.md`.
6. User-facing API or CLI changes update the README in the same PR. Do not refresh the README status line for internal-only slices.
7. Public docs (README, ADRs, CONTRIBUTING, PR body) stay vendor-neutral: describe TenseMem by its properties, not by naming other products.
8. No secrets, tokens, or database files in the commit.

Body must include **Issue**, **What**, **Why**, and **Docs** (or “none needed” plus one line). Studio UI PRs also need **UI** with media.

## Commits

Imperative mood (`Add freshness fields to context reads`). Group related changes. No `--no-verify`.

## Releasing to PyPI

Version lives in `src/tensemem/__init__.py` (`__version__`). Update `CHANGELOG.md` in the same PR as the version bump when you cut a release.

1. On [PyPI](https://pypi.org/manage/project/tensemem/settings/publishing/), add a **trusted publisher** for this GitHub repo: workflow `publish.yml`, environment `pypi`. No API token in GitHub secrets.
2. In this repo, create a GitHub Environment named `pypi` (optional protection rules for who can push tags).
3. Merge the release PR to `main`, then tag and push (tag must match `__version__` exactly, with a `v` prefix):

```bash
git checkout main && git pull
git tag v0.1.0
git push origin v0.1.0
```

4. The **Publish** workflow builds, runs `twine check`, and uploads with OIDC. Create a GitHub Release from that tag and paste the matching `CHANGELOG.md` section.

Do not store a PyPI password or API token in the repository.

## Public surface

- `Memory` / `AsyncMemory` default to SQLite. `store=` takes a `SqliteBackend` (ADR 0020). A second SQL dialect is out of scope until its repositories exist.
- Extract adapters live under `src/tensemem/providers/llm/`. Gemini is `generateContent` + `GEMINI_API_KEY`; it is not a LiteLLM model id in Token.
- Docs site is `docs/` + `mkdocs.yml` (`uvx mkdocs serve`).
- Property tests: `tests/property/` (40 examples in CI; `HYPOTHESIS_PROFILE=dev` for a longer run).
- Golden extract: `tests/golden/v1.jsonl` via `python -m tensemem.eval`.
- Bench: `tensemem bench` (packaged TenseBench). `tensemem longmem --llm` / `tensemem locomo --llm` are local-only; CI never passes `--llm`.

Agents and editors should follow [`.cursor/rules/`](.cursor/rules/).
