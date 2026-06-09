"""Output rendering: pretty (rich), JSON and TOON.

``rich`` is for humans (tables for lists of records, syntax-highlighted trees
otherwise), ``json`` is canonical machine output, and ``toon`` emits the
token-efficient Token-Oriented Object Notation via the :mod:`toons` package.
"""

from __future__ import annotations

import enum
import json
from typing import Any

import toons
from rich.console import Console
from rich.json import JSON
from rich.table import Table


class OutputFormat(enum.StrEnum):
    """Supported rendering formats."""

    RICH = "rich"
    JSON = "json"
    TOON = "toon"


def render(data: Any, fmt: OutputFormat, *, console: Console | None = None) -> None:
    """Render ``data`` to stdout in the requested format."""
    if fmt is OutputFormat.JSON:
        print(to_json(data))
        return
    if fmt is OutputFormat.TOON:
        print(to_toon(data))
        return
    _render_rich(data, console or Console())


def to_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def to_toon(data: Any) -> str:
    return toons.dumps(data)


# Above this many columns a table squishes unreadably; show JSON instead.
_MAX_TABLE_COLUMNS = 8


def _render_rich(data: Any, console: Console) -> None:
    rows = _as_record_list(data)
    if rows is not None and _column_count(rows) <= _MAX_TABLE_COLUMNS:
        console.print(_records_table(rows))
        return
    console.print(JSON(to_json(data)))


def _column_count(rows: list[dict[str, Any]]) -> int:
    columns: set[str] = set()
    for row in rows:
        columns.update(row)
    return len(columns)


def _as_record_list(data: Any) -> list[dict[str, Any]] | None:
    """Return ``data`` as a list of flat-ish dict records, or ``None``.

    Unwraps the Holded v2 ``{items: [...], cursor, has_more}`` envelope.
    """
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        data = data["items"]
    if isinstance(data, list) and data and all(isinstance(item, dict) for item in data):
        return data
    return None


def _records_table(rows: list[dict[str, Any]]) -> Table:
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    table = Table(show_lines=False, header_style="bold cyan")
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*[_cell(row.get(column)) for column in columns])
    return table


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)
