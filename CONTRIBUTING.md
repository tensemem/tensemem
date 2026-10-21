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

Run these from the repo root before you push. CI runs the same set.

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest
uvx codespell --skip="*.lock,.git,uv.lock" --ignore-words-list="tensemem"
```

Default pytest never calls a model. After `uv sync --extra openai`:

```bash
TENSEMEM_LIVE=1 uv run pytest -m live
```

| Check | What it does |
|---|---|
| **CI** | Aggregator. Green only when lint, the full OS/Python test matrix, and the package build all pass |
| **Lint and type-check** | Ruff, format, pyright, codespell |
| **Test (`os`, Python `x`)** | `pytest` on Ubuntu / macOS / Windows × 3.11–3.15 |
| **Build distributions** | `uv build` + `twine check` |
| **PR quality** | Aggregator. Green only when description/size, actionlint, and gitleaks pass |
| **PR description and size** | Requires `## What` / `## Why` / `## Docs`; fails diffs over 1000 lines unless labeled `large-pr` |
| **CodeQL** | `Analyze (python)` and `Analyze (actions)` |
| **Live extract** | Not a merge gate. A repo admin comments `/test` to run `pytest -m live` on the default branch only, so unmerged code never sees hosted keys |

`main` cannot merge while any required check is red or pending. Required checks are **CI**, **PR quality**, **Analyze (python)**, and **Analyze (actions)**. Admins are not exempt. Force-pushes and deleting `main` stay blocked. Live extract is optional and must stay that way.

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

## Pull requests

`main` is protected and cannot merge while required checks are red or pending. One concern per PR.

1. Title includes exactly one of `[low-risk]`, `[medium-risk]`, `[high-risk]`.
2. Add **one** new file `changes/<kebab-slug>.md` (What + Why), unless the title includes `[no-changeset]`.
3. Significant design choices get an ADR in `docs/adr/` and a row in `docs/adr/README.md`.
4. User-facing API or CLI changes update the README in the same PR. Do not refresh the README status line for internal-only slices.
5. Public docs (README, ADRs, CONTRIBUTING, PR body) stay vendor-neutral: describe TenseMem by its properties, not by naming other products.
6. No secrets, tokens, or database files in the commit.

Body must include **What**, **Why**, and **Docs** (or “none needed” plus one line).

## Commits

Imperative mood (`Add freshness fields to context reads`). Group related changes. No `--no-verify`.

## Public surface

- `Memory` / `AsyncMemory` default to SQLite. `store=` takes a `SqliteBackend` (ADR 0020). A second SQL dialect is out of scope until its repositories exist.
- Extract adapters live under `src/tensemem/providers/llm/`. Gemini is `generateContent` + `GEMINI_API_KEY`; it is not a LiteLLM model id in Token.
- Docs site is `docs/` + `mkdocs.yml` (`uvx mkdocs serve`).
- Property tests: `tests/property/` (40 examples in CI; `HYPOTHESIS_PROFILE=dev` for a longer run).
- Golden extract: `tests/golden/v1.jsonl` via `python -m tensemem.eval`.
- Bench: `tensemem bench` (packaged TenseBench). `tensemem longmem --llm` / `tensemem locomo --llm` are local-only; CI never passes `--llm`.

Agents and editors should follow [`.cursor/rules/`](.cursor/rules/).
