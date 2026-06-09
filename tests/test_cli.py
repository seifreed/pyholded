"""CLI helper tests."""

from __future__ import annotations

import click
import pytest

from pyholded.cli import _parse_data


def test_parse_data_valid_json() -> None:
    assert _parse_data('{"name": "ACME"}', ()) == {"name": "ACME"}


def test_parse_data_fields_only() -> None:
    assert _parse_data(None, ("name=ACME", "code=B1")) == {"name": "ACME", "code": "B1"}


def test_parse_data_invalid_json_raises_clean_error() -> None:
    # Regression: invalid --data must surface a BadParameter, not a raw traceback.
    with pytest.raises(click.BadParameter):
        _parse_data("{not valid", ())


def test_parse_data_missing_file_raises_clean_error() -> None:
    with pytest.raises(click.BadParameter):
        _parse_data("@/nonexistent/path/data.json", ())
