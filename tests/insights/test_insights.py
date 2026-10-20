from typing import cast

from tensemem import FakeExtractor, Memory
from tensemem.insights import act_risk, compare, echo, seed_sample
from tensemem.mcp import seed_starter


def test_sample_compare_echo_and_act_risk() -> None:
    with Memory(":memory:", llm=FakeExtractor(), start_worker=False) as mem:
        seed_starter(mem)
        seeded = seed_sample(mem)
        values = _map(seeded, "values")
        freshness = _map(seeded, "freshness")
        assert values["files_return"] == "GSTR-3B"
        assert freshness["is_current"] is True

        risk = act_risk(mem, "studio-demo")
        assert risk["verdict"] == "act"
        assert _map(risk, "values")["invoice_currency"] == "EUR"

        compared = compare(mem, "studio-demo", "which GST return do we file")
        tensemem = _map(compared, "tensemem")
        concat = _map(compared, "concat")
        stale = compared["stale"]
        assert isinstance(stale, list)
        assert "GSTR-3B" in str(tensemem["text"])
        assert "GSTR-1" in stale
        stale_present = concat["stale_present"]
        assert isinstance(stale_present, list)
        assert "GSTR-1" in stale_present

        echoed = echo(mem, "studio-demo", turns=3)
        assert echoed["turns"] == 3
        assert echoed["flat"] is True
        series = echoed["series"]
        assert isinstance(series, list)
        rows = cast(list[object], series)
        assert len(rows) == 4


def _map(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)
