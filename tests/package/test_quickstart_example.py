from pathlib import Path
from runpy import run_path


def test_quickstart_example_runs() -> None:
    path = Path(__file__).resolve().parents[2] / "examples" / "quickstart.py"
    run_path(str(path))
