"""Print golden-set scores, TenseBench, LongMemEval, LoCoMo, or context() latency."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tensemem.eval.golden import default_cases_path, evaluate, load_cases
from tensemem.eval.latency import format_report as format_latency
from tensemem.eval.latency import run_latency
from tensemem.eval.tensebench import format_report, run_suite
from tensemem.providers.llm.fake import FakeExtractor


def main(argv: list[str] | None = None) -> None:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw[:1] == ["bench"]:
        _bench(raw[1:])
        return
    if raw[:1] == ["latency"]:
        _latency(raw[1:])
        return
    if raw[:1] == ["longmem"]:
        _longmem(raw[1:])
        return
    if raw[:1] == ["locomo"]:
        _locomo(raw[1:])
        return
    parser = argparse.ArgumentParser(description="Score extract against labeled utterances.")
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="JSONL cases (default: tests/golden/v1.jsonl)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="include skip_fake cases (needs a real provider to be meaningful)",
    )
    args = parser.parse_args(raw)
    path = args.path or default_cases_path()
    report = evaluate(FakeExtractor(), load_cases(path), skip_fake=not args.all)
    print(f"cases: {report.cases}  skipped: {report.skipped}")
    print(f"precision: {report.precision:.3f}  recall: {report.recall:.3f}")
    for name, (precision, recall, count) in report.by_category.items():
        print(f"  {name}: p={precision:.3f} r={recall:.3f} n={count}")


def _bench(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Score TenseBench scenarios.")
    parser.add_argument("--path", type=Path, default=None)
    args = parser.parse_args(argv)
    print(format_report(run_suite(args.path)))


def _latency(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Time empty-query context() reads.")
    parser.add_argument("--facts", type=int, default=None)
    parser.add_argument("--rounds", type=int, default=None)
    args = parser.parse_args(argv)
    kwargs: dict[str, int] = {}
    if args.facts is not None:
        kwargs["facts"] = args.facts
    if args.rounds is not None:
        kwargs["rounds"] = args.rounds
    print(format_latency(run_latency(**kwargs)))


def _longmem(argv: list[str]) -> None:
    from tensemem.eval.longmem import format_report as format_longmem
    from tensemem.eval.longmem import run_longmem

    parser = argparse.ArgumentParser(description="Score a LongMemEval-shaped pack.")
    parser.add_argument("--path", type=Path, default=None)
    parser.add_argument(
        "--llm",
        default=None,
        choices=["openai", "anthropic", "ollama", "litellm", "fake"],
    )
    args = parser.parse_args(argv)
    from tensemem.eval.hosted import provider_from_name

    print(format_longmem(run_longmem(args.path, llm=provider_from_name(args.llm))))


def _locomo(argv: list[str]) -> None:
    from tensemem.eval.locomo import format_report as format_locomo
    from tensemem.eval.locomo import run_locomo

    parser = argparse.ArgumentParser(description="Score a LoCoMo-shaped pack.")
    parser.add_argument("--path", type=Path, default=None)
    parser.add_argument(
        "--llm",
        default=None,
        choices=["openai", "anthropic", "ollama", "litellm", "fake"],
    )
    args = parser.parse_args(argv)
    from tensemem.eval.hosted import provider_from_name

    print(format_locomo(run_locomo(args.path, llm=provider_from_name(args.llm))))


if __name__ == "__main__":
    main()
