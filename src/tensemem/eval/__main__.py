"""Print golden-set precision and recall. Default provider is FakeExtractor."""

from __future__ import annotations

import argparse
from pathlib import Path

from tensemem.eval.golden import default_cases_path, evaluate, load_cases
from tensemem.providers.llm.fake import FakeExtractor


def main(argv: list[str] | None = None) -> None:
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
    args = parser.parse_args(argv)
    path = args.path or default_cases_path()
    report = evaluate(FakeExtractor(), load_cases(path), skip_fake=not args.all)
    print(f"cases: {report.cases}  skipped: {report.skipped}")
    print(f"precision: {report.precision:.3f}  recall: {report.recall:.3f}")
    for name, (precision, recall, count) in report.by_category.items():
        print(f"  {name}: p={precision:.3f} r={recall:.3f} n={count}")


if __name__ == "__main__":
    main()
