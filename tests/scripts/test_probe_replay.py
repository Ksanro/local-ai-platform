"""Tests for the offline probe-replay comparison (``scripts/probe_replay.py``)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.probe_replay import compare, main


def _row(facts: list[str], sent: list[str], maximum: int = 2) -> dict[str, object]:
    return {
        "intent": "SEARCH",
        "primary": sent[0] if sent else None,
        "sent": sent,
        "facts_present": facts,
        "facts": len(facts),
        "max": maximum,
    }


def test_identical_replays_are_ok() -> None:
    rows = {"a": _row(["x"], ["m.f"]), "b": _row([], ["m.g"])}

    lines = compare(rows, rows)

    assert lines[0].startswith("OK")
    assert "facts present 1 -> 1 of 4" in lines[0]
    assert "2 of 2 probes send identical symbols" in lines[0]
    assert len(lines) == 1


def test_gain_on_one_probe_is_ok_and_reported() -> None:
    base = {"a": _row([], ["m.f"]), "b": _row(["y"], ["m.g"])}
    new = {"a": _row(["x"], ["m.f", "m.h"]), "b": _row(["y"], ["m.g"])}

    lines = compare(base, new)

    assert lines[0].startswith("OK")
    assert any(line.startswith("a: facts 0->1/2") and "gained=['x']" in line for line in lines)


def test_any_lost_fact_is_a_regression_even_if_total_rises() -> None:
    base = {"a": _row([], ["m.f"]), "b": _row(["y"], ["m.g"])}
    new = {"a": _row(["x", "z"], ["m.f"]), "b": _row([], ["m.k"])}

    lines = compare(base, new)

    assert lines[0].startswith("REGRESSION b")
    assert "facts present 1 -> 2 of 4" in lines[0]


def test_missing_probe_is_a_regression() -> None:
    base = {"a": _row(["x"], ["m.f"])}

    assert compare(base, {})[0].startswith("REGRESSION a")


def test_cli_compare_exit_code(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    new = tmp_path / "new.json"
    base.write_text(json.dumps({"a": _row(["x"], ["m.f"])}), encoding="utf-8")
    new.write_text(json.dumps({"a": _row([], ["m.f"])}), encoding="utf-8")

    assert main(["--compare", str(base), str(base)]) == 0
    assert main(["--compare", str(base), str(new)]) == 1
