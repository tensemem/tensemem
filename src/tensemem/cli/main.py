"""Inspect a TenseMem SQLite file from the shell (argparse, no extra deps)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

from tensemem.core.errors import UnknownFactError, UnknownJobError
from tensemem.core.models import FactSet, FactView, JobView, MemoryStats
from tensemem.memory import Memory

_DEFAULT_DB = "tensemem.db"


class _Scope(TypedDict):
    agent_id: str
    namespace: str


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    try:
        return int(handler(args))
    except (UnknownFactError, UnknownJobError, ValueError, FileNotFoundError) as extra:
        print(extra, file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tensemem", description="Inspect TenseMem state.")
    parser.add_argument("--db", default=_DEFAULT_DB, help="SQLite file (default: tensemem.db)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    parser.add_argument("--agent", default="", dest="agent_id")
    parser.add_argument("--namespace", default="default")
    sub = parser.add_subparsers(dest="command")

    inspect = sub.add_parser("inspect", help="ACTIVE facts for a user")
    inspect.add_argument("--user", required=True)
    inspect.set_defaults(handler=_cmd_inspect)

    history = sub.add_parser("history", help="version chain for a predicate")
    history.add_argument("--user", required=True)
    history.add_argument("predicate", nargs="?")
    history.set_defaults(handler=_cmd_history)

    explain = sub.add_parser("explain", help="provenance for one fact id")
    explain.add_argument("fact_id")
    explain.set_defaults(handler=_cmd_explain)

    search = sub.add_parser("search", help="ranked facts and episodes")
    search.add_argument("--user", required=True)
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(handler=_cmd_search)

    jobs = sub.add_parser("jobs", help="list or manage the extract outbox")
    jobs.add_argument(
        "action",
        nargs="?",
        default="list",
        choices=["list", "retry", "dismiss", "purge-dead"],
    )
    jobs.add_argument("job_id", nargs="?")
    jobs.add_argument("--user")
    jobs.set_defaults(handler=_cmd_jobs)

    freshness = sub.add_parser("freshness", help="watermark and pending counts")
    freshness.add_argument("--user", required=True)
    freshness.set_defaults(handler=_cmd_freshness)

    correct = sub.add_parser("correct", help="reject a fact (and optional replacement)")
    correct.add_argument("fact_id")
    correct.add_argument("--replace")
    correct.add_argument("--note")
    correct.set_defaults(handler=_cmd_correct)

    export_p = sub.add_parser("export", help="JSONL of predicates and episodes")
    export_p.add_argument("--user", required=True)
    export_p.add_argument("--out", type=Path)
    export_p.set_defaults(handler=_cmd_export)

    import_p = sub.add_parser("import", help="replay a JSONL dump")
    import_p.add_argument("--user", required=True)
    import_p.add_argument("path", type=Path)
    import_p.set_defaults(handler=_cmd_import)

    rebuild = sub.add_parser("rebuild", help="replay explicit ops; re-queue messages")
    rebuild.add_argument("--user", required=True)
    rebuild.set_defaults(handler=_cmd_rebuild)

    backup = sub.add_parser("backup", help="copy the database with SQLite backup")
    backup.add_argument("dest", type=Path)
    backup.set_defaults(handler=_cmd_backup)

    stats = sub.add_parser("stats", help="counts and a rough token estimate")
    stats.add_argument("--user")
    stats.set_defaults(handler=_cmd_stats)

    bench = sub.add_parser("bench", help="run TenseBench (no database required)")
    bench.add_argument("--path", type=Path, default=None, help="JSONL scenarios")
    bench.add_argument(
        "--system",
        action="append",
        dest="systems",
        choices=["tensemem", "concat", "similarity"],
        help="repeat to choose systems (default: all)",
    )
    bench.set_defaults(handler=_cmd_bench)

    longmem = sub.add_parser("longmem", help="score a LongMemEval-shaped pack (no database)")
    longmem.add_argument("--path", type=Path, default=None, help="JSON array or JSONL")
    longmem.set_defaults(handler=_cmd_longmem)

    locomo = sub.add_parser("locomo", help="score a LoCoMo-shaped pack (no database)")
    locomo.add_argument("--path", type=Path, default=None, help="JSON array or JSONL")
    locomo.set_defaults(handler=_cmd_locomo)

    mcp_p = sub.add_parser("mcp", help="stdio MCP server (needs tensemem[mcp])")
    mcp_p.add_argument("--user", default="", help="default user_id when a tool omits it")
    mcp_p.set_defaults(handler=_cmd_mcp)

    serve_p = sub.add_parser("serve", help="REST server (needs tensemem[server])")
    serve_p.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind address (default 127.0.0.1; non-loopback needs a TLS proxy)",
    )
    serve_p.add_argument("--port", type=int, default=8080)
    serve_p.set_defaults(handler=_cmd_serve)

    latency = sub.add_parser("latency", help="time empty-query context() (no database required)")
    latency.add_argument(
        "--facts",
        type=int,
        default=None,
        help="ACTIVE facts to seed (default 5000)",
    )
    latency.add_argument("--rounds", type=int, default=None, help="timed reads (default 80)")
    latency.set_defaults(handler=_cmd_latency)
    return parser


def _open(args: argparse.Namespace, *, create: bool = False) -> Memory:
    if not create and not _db_present(args.db):
        raise FileNotFoundError(f"database not found: {args.db}")
    return Memory(args.db, start_worker=False)


def _db_present(path: str) -> bool:
    text = str(path)
    if text == ":memory:" or text.startswith("file:"):
        return True
    return Path(text).expanduser().exists()


def _scope(args: argparse.Namespace) -> _Scope:
    return {"agent_id": args.agent_id, "namespace": args.namespace}


def _cmd_inspect(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        state = mem.state(args.user, **_scope(args))
        return _print_facts(args, state)


def _cmd_history(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        history = mem.history(args.user, args.predicate, **_scope(args))
        return _print_facts(args, history)


def _cmd_explain(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        explained = mem.explain(args.fact_id)
        if args.json:
            print(json.dumps(explained.model_dump(mode="json"), indent=2))
            return 0
        fact = explained.fact
        print(f"{fact.id}  {fact.subject}.{fact.predicate}={fact.object}  {fact.status.value}")
        if explained.superseded_by:
            print(f"superseded_by  {explained.superseded_by}")
        if explained.evidence_episode_ids:
            print("evidence  " + ",".join(str(i) for i in explained.evidence_episode_ids))
        for event in explained.events:
            src = event.from_status.value if event.from_status is not None else "-"
            print(f"{event.at}  {src}->{event.to_status.value}  {event.reason}")
        return 0


def _cmd_search(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        result = mem.search(args.user, args.query, limit=args.limit, **_scope(args))
        if args.json:
            print(json.dumps(result.model_dump(mode="json"), indent=2))
            return 0
        if not result.hits:
            print("no hits")
            return 0
        rows = [
            [hit.kind, f"{hit.score:.3f}", hit.predicate or "-", hit.text] for hit in result.hits
        ]
        print(_table(["kind", "score", "predicate", "text"], rows))
        return 0


def _cmd_jobs(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        if args.action == "retry":
            if not args.job_id:
                print("jobs retry needs a job id", file=sys.stderr)
                return 1
            job = mem.retry_job(args.job_id)
            print(_job_line(job))
            return 0
        if args.action == "dismiss":
            if not args.job_id:
                print("jobs dismiss needs a job id", file=sys.stderr)
                return 1
            job = mem.dismiss_job(args.job_id)
            print(_job_line(job))
            return 0
        if args.action == "purge-dead":
            dismissed = mem.dismiss_dead_jobs(args.user, **_scope(args))
            if args.json:
                print(json.dumps([job.model_dump(mode="json") for job in dismissed], indent=2))
                return 0
            print(f"dismissed {len(dismissed)}")
            return 0
        jobs = mem.jobs(args.user, **_scope(args))
        return _print_jobs(args, jobs)


def _cmd_freshness(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        fresh = mem.state(args.user, **_scope(args)).freshness
        if args.json:
            print(json.dumps(fresh.model_dump(mode="json"), indent=2))
            return 0
        print(
            f"as_of_seq={fresh.as_of_seq}  latest_seq={fresh.latest_seq}  "
            f"pending={fresh.pending}  failed={fresh.failed}  "
            f"projection_version={fresh.projection_version}  current={fresh.is_current}"
        )
        return 0


def _cmd_correct(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        result = mem.correct(args.fact_id, replacement=args.replace, note=args.note)
        print(f"seq={result.seq}")
        return 0


def _cmd_export(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        text = mem.export_jsonl(args.user, **_scope(args))
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    with _open(args, create=True) as mem:
        n = mem.import_jsonl(args.user, args.path, **_scope(args))
    print(f"imported {n}")
    return 0


def _cmd_rebuild(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        version = mem.rebuild(args.user, **_scope(args))
    print(f"projection_version={version}")
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        mem.backup(args.dest)
    print(args.dest)
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    with _open(args) as mem:
        stats = mem.stats(args.user, **_scope(args))
        if args.json:
            print(json.dumps(stats.model_dump(mode="json"), indent=2))
            return 0
        print(_stats_text(stats))
        return 0


def _cmd_bench(args: argparse.Namespace) -> int:
    from tensemem.eval.tensebench import format_report, run_suite

    report = run_suite(args.path, systems=args.systems)
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return 0
    print(format_report(report))
    return 0


def _cmd_longmem(args: argparse.Namespace) -> int:
    from tensemem.eval.longmem import format_report, run_longmem

    report = run_longmem(args.path)
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return 0
    print(format_report(report))
    return 0


def _cmd_locomo(args: argparse.Namespace) -> int:
    from tensemem.eval.locomo import format_report, run_locomo

    report = run_locomo(args.path)
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return 0
    print(format_report(report))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from tensemem.server import serve

    try:
        serve(
            args.db,
            host=args.host,
            port=args.port,
            agent_id=args.agent_id,
            namespace=args.namespace,
        )
    except RuntimeError as extra:
        print(extra, file=sys.stderr)
        return 1
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    from tensemem.mcp import serve

    try:
        serve(
            args.db,
            default_user=args.user,
            agent_id=args.agent_id,
            namespace=args.namespace,
        )
    except RuntimeError as extra:
        print(extra, file=sys.stderr)
        return 1
    return 0


def _cmd_latency(args: argparse.Namespace) -> int:
    from tensemem.eval.latency import format_report, run_latency

    kwargs: dict[str, int] = {}
    if args.facts is not None:
        kwargs["facts"] = args.facts
    if args.rounds is not None:
        kwargs["rounds"] = args.rounds
    report = run_latency(**kwargs)
    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return 0
    print(format_report(report))
    return 0


def _print_facts(args: argparse.Namespace, payload: FactSet) -> int:
    if args.json:
        print(json.dumps(payload.model_dump(mode="json"), indent=2))
        return 0
    if not payload.facts:
        print("no facts")
        return 0
    rows = [_fact_row(fact) for fact in payload.facts]
    print(_table(["id", "subject", "predicate", "object", "status"], rows))
    return 0


def _fact_row(fact: FactView) -> list[str]:
    return [fact.id, fact.subject, fact.predicate, fact.object, fact.status.value]


def _print_jobs(args: argparse.Namespace, jobs: tuple[JobView, ...]) -> int:
    if args.json:
        print(json.dumps([job.model_dump(mode="json") for job in jobs], indent=2))
        return 0
    if not jobs:
        print("no jobs")
        return 0
    rows = [
        [job.id, job.kind.value, job.status.value, str(job.attempts), job.last_error or "-"]
        for job in jobs
    ]
    print(_table(["id", "kind", "status", "attempts", "error"], rows))
    return 0


def _job_line(job: JobView) -> str:
    return f"{job.id}  {job.kind.value}  {job.status.value}"


def _stats_text(stats: MemoryStats) -> str:
    facts = ",".join(f"{k}={v}" for k, v in sorted(stats.facts_by_status.items())) or "-"
    jobs = ",".join(f"{k}={v}" for k, v in sorted(stats.jobs_by_status.items())) or "-"
    return (
        f"scopes={stats.scopes}  episodes={stats.episodes}  facts={stats.facts}  "
        f"queue_depth={stats.queue_depth}  pending={stats.pending_episodes}  "
        f"failed={stats.failed_episodes}  rejected={stats.rejected_claims}  "
        f"estimated_tokens={stats.estimated_tokens}  "
        f"projection_version={stats.projection_version}\n"
        f"facts_by_status={facts}\n"
        f"jobs_by_status={jobs}"
    )


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt(headers), fmt(["-" * width for width in widths])]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)
