"""Output formatter tests."""

from __future__ import annotations

import json

import pytest

from pyholded.output import OutputFormat, render, to_json, to_toon

RECORDS = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]


def test_to_json_roundtrip() -> None:
    assert json.loads(to_json(RECORDS)) == RECORDS


def test_to_toon_is_compact() -> None:
    toon = to_toon(RECORDS)
    assert "Alice" in toon
    assert "Bob" in toon
    # TOON declares the row count and field header for uniform arrays.
    assert "[2]" in toon


def test_render_json(capsys: pytest.CaptureFixture[str]) -> None:
    render(RECORDS, OutputFormat.JSON)
    captured = capsys.readouterr()
    assert json.loads(captured.out) == RECORDS


def test_render_toon(capsys: pytest.CaptureFixture[str]) -> None:
    render({"k": "v"}, OutputFormat.TOON)
    assert "k" in capsys.readouterr().out


def test_render_rich_table(capsys: pytest.CaptureFixture[str]) -> None:
    render(RECORDS, OutputFormat.RICH)
    out = capsys.readouterr().out
    assert "Alice" in out
    assert "name" in out


def test_render_rich_unwraps_items_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    render({"items": RECORDS, "cursor": None, "has_more": False}, OutputFormat.RICH)
    out = capsys.readouterr().out
    assert "Alice" in out
    assert "name" in out


def test_render_rich_falls_back_to_json_for_non_records(capsys: pytest.CaptureFixture[str]) -> None:
    render({"k": "v"}, OutputFormat.RICH)
    assert "k" in capsys.readouterr().out


def test_render_rich_cells_render_none_and_nested(capsys: pytest.CaptureFixture[str]) -> None:
    render([{"id": 1, "note": None, "meta": {"x": 1}}], OutputFormat.RICH)
    out = capsys.readouterr().out
    assert "id" in out
    assert "meta" in out


def test_render_rich_wide_records_fall_back_to_json(capsys: pytest.CaptureFixture[str]) -> None:
    # More columns than a table can show legibly: fall back to JSON.
    render([{f"c{i}": i for i in range(9)}], OutputFormat.RICH)
    assert "c0" in capsys.readouterr().out
