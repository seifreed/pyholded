"""CLI tests: helpers plus the registry-driven command tree over a stub transport."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from pyholded.cli import _parse_data, _register_resources, cli, main

BASE = "https://api.holded.test/api/v2/"
_ABORT_EXIT_CODE = 130


@pytest.fixture(autouse=True)
def _registered() -> None:
    _register_resources()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "HOLDED_TOKEN",
        "HOLDED_API_KEY",
        "HOLDED_CONFIG",
        "HOLDED_TOKEN_ACME",
        "HOLDED_TOKEN_PERSONAL",
    ):
        monkeypatch.delenv(key, raising=False)


def _args(*rest: str) -> list[str]:
    return ["--token", "tkn", "--base-url", BASE, "--config", "/none.toml", *rest]


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


def test_parse_data_reads_from_file(tmp_path: Path) -> None:
    path = tmp_path / "body.json"
    path.write_text('{"name": "FromFile"}', encoding="utf-8")
    assert _parse_data(f"@{path}", ()) == {"name": "FromFile"}


def test_resources_command_lists_registry() -> None:
    result = CliRunner().invoke(cli, ["resources", "-o", "json"])
    assert result.exit_code == 0, result.output
    assert "contacts" in result.output


def test_resources_command_uses_group_default_format() -> None:
    result = CliRunner().invoke(cli, ["--output", "json", "resources"])
    assert result.exit_code == 0, result.output
    assert "contacts" in result.output


def test_accounts_command_lists_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "tok-acme")
    result = CliRunner().invoke(cli, ["--config", "/none.toml", "accounts", "-o", "json"])
    assert result.exit_code == 0, result.output
    assert "acme" in result.output


def test_operation_get_list(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}contacts", json={"items": [{"id": "1"}]})
    result = CliRunner().invoke(cli, _args("contacts", "list", "-o", "json"))
    assert result.exit_code == 0, result.output
    assert "1" in result.output


def test_operation_get_with_path_param(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}invoices/abc", json={"id": "abc"})
    result = CliRunner().invoke(cli, _args("invoices", "get", "--id", "abc", "-o", "json"))
    assert result.exit_code == 0, result.output
    assert "abc" in result.output


def test_operation_with_query_param(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}contacts?limit=5", json={"items": []})
    result = CliRunner().invoke(cli, _args("contacts", "list", "--limit", "5", "-o", "json"))
    assert result.exit_code == 0, result.output


def test_operation_create_with_field(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}contacts", method="POST", json={"id": "new"})
    result = CliRunner().invoke(
        cli, _args("contacts", "create", "--field", "name=ACME", "-o", "json")
    )
    assert result.exit_code == 0, result.output
    assert "new" in result.output


def test_operation_fetch_all_flag(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}contacts", json={"items": [{"id": "1"}], "cursor": None, "has_more": False}
    )
    result = CliRunner().invoke(cli, _args("contacts", "list", "--all", "-o", "json"))
    assert result.exit_code == 0, result.output
    assert "1" in result.output


def test_all_accounts_call_fans_out(httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "a")
    monkeypatch.setenv("HOLDED_TOKEN_PERSONAL", "b")
    httpx_mock.add_response(json={"items": []})
    httpx_mock.add_response(json={"items": []})
    result = CliRunner().invoke(
        cli, ["--all-accounts", "--config", "/none.toml", "contacts", "list", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    assert "acme" in result.output
    assert "personal" in result.output


def test_raw_get(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}taxes?limit=5", json={"items": [{"id": "t1"}]})
    result = CliRunner().invoke(
        cli, _args("raw", "GET", "/taxes", "--param", "limit=5", "-o", "json")
    )
    assert result.exit_code == 0, result.output
    assert "t1" in result.output


def test_raw_post_data(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}contacts", method="POST", json={"id": "x"})
    result = CliRunner().invoke(
        cli, _args("raw", "POST", "contacts", "--data", '{"name": "ACME"}', "-o", "json")
    )
    assert result.exit_code == 0, result.output
    assert "x" in result.output


def test_raw_binary_writes_bytes(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}invoices/x/pdf", content=b"%PDF-1.4")
    result = CliRunner().invoke(cli, _args("raw", "GET", "invoices/x/pdf", "--binary"))
    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == b"%PDF-1.4"


def test_raw_all_accounts(httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "a")
    monkeypatch.setenv("HOLDED_TOKEN_PERSONAL", "b")
    httpx_mock.add_response(json={"items": []})
    httpx_mock.add_response(json={"items": []})
    result = CliRunner().invoke(
        cli, ["--all-accounts", "--config", "/none.toml", "raw", "GET", "taxes", "-o", "json"]
    )
    assert result.exit_code == 0, result.output
    assert "acme" in result.output


def test_main_runs_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["holded", "resources", "-o", "json"])
    main()
    assert "contacts" in capsys.readouterr().out


def test_main_maps_holded_error_to_exit_1(
    monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url=f"{BASE}invoices/x", status_code=404, json={"message": "nope"})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "holded",
            "--token",
            "tkn",
            "--base-url",
            BASE,
            "--config",
            "/none.toml",
            "invoices",
            "get",
            "--id",
            "x",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_maps_click_exception_to_its_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["holded", "--output", "bogus", "resources"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code != 0


def test_main_maps_abort_to_exit_130(monkeypatch: pytest.MonkeyPatch) -> None:
    def _abort(**_kwargs: object) -> None:
        raise click.exceptions.Abort

    monkeypatch.setattr(cli, "main", _abort)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == _ABORT_EXIT_CODE


def test_module_executes_as_script(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["holded", "resources", "-o", "json"])
    # Drop the cached module so runpy re-executes it cleanly as ``__main__``.
    monkeypatch.delitem(sys.modules, "pyholded.cli", raising=False)
    runpy.run_module("pyholded.cli", run_name="__main__")
    assert "contacts" in capsys.readouterr().out
