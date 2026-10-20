import json
from importlib.resources import files
from pathlib import Path

from tensemem.eval.locomo import (
    default_samples_path,
    format_report,
    load_samples,
    run_locomo,
    session_stamp,
)


def test_packaged_pilot_covers_every_published_category() -> None:
    samples = load_samples()
    assert len(samples) == 1
    assert samples[0].sample_id == "locomo-gst-itinerary"
    assert {qa.category for qa in samples[0].qa} == {1, 2, 3, 4, 5}
    packed = files("tensemem.eval").joinpath("locomo_pilot.json")
    assert packed.is_file()
    blob = packed.read_text(encoding="utf-8")
    assert "Delhi" not in blob
    assert "Bangalore" not in blob
    assert default_samples_path().name == "locomo_pilot.json"


def test_pilot_meets_category_slos() -> None:
    report = run_locomo()
    assert report.conversations == 1
    assert report.cases == 5
    assert report.accuracy == 1.0
    for name in ("multi-hop", "temporal", "open-domain", "single-hop", "adversarial"):
        score = report.by_type[name]
        assert score.n == 1
        assert score.accuracy == 1.0
    text = format_report(report)
    assert "LoCoMo adapter" in text
    assert "multi-hop:" in text
    assert "adversarial:" in text


def test_load_jsonl_and_empty_answer(tmp_path: Path) -> None:
    path = tmp_path / "one.jsonl"
    path.write_text(
        json.dumps(
            {
                "sample_id": "empty",
                "conversation": {
                    "speaker_a": "Priya",
                    "session_1": [{"speaker": "Priya", "text": "thanks"}],
                },
                "qa": [
                    {
                        "question": "what is filed",
                        "answer": "",
                        "category": 4,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    samples = load_samples(path)
    assert len(samples) == 1
    assert samples[0].qa[0].answer == ""
    report = run_locomo(path)
    assert report.ok == 0
    assert report.cases == 1
    assert report.conversations == 1


def test_official_adversarial_without_trap_is_unscored(tmp_path: Path) -> None:
    path = tmp_path / "adv.json"
    path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "official-adv",
                    "conversation": {
                        "speaker_a": "Priya",
                        "session_1": [{"speaker": "Priya", "text": "thanks"}],
                    },
                    "qa": [
                        {
                            "question": "Are we staying in Bali?",
                            "answer": "The conversation does not mention a stay in Bali.",
                            "category": 5,
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    report = run_locomo(path)
    assert report.cases == 0
    assert report.ok == 0
    assert report.by_type["adversarial"].n == 0
    assert report.by_type["adversarial"].accuracy is None


def test_session_stamp_keeps_locomo_time_and_drops_unknown() -> None:
    stamp = session_stamp("9:00 am on 1 June, 2026")
    assert stamp == "2026-06-01T09:00:00.000000Z"
    assert session_stamp("2026-03-01") == "2026-03-01T00:00:00.000000Z"
    assert session_stamp("not a date") is None
