"""Multi-account configuration and MultiClient fan-out tests."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from pyholded import HoldedClient, MultiClient
from pyholded.config import resolve_accounts, resolve_config
from pyholded.exceptions import ConfigError
from pyholded.transport import Transport

BASE = "https://api.holded.test/api/v2/"


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("HOLDED_TOKEN", "HOLDED_API_KEY", "HOLDED_TOKEN_ACME", "HOLDED_TOKEN_PERSONAL"):
        monkeypatch.delenv(key, raising=False)


def test_named_accounts_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("HOLDED_TOKEN", "tok-default")
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "tok-acme")
    accounts = resolve_accounts(Path("/none.toml"))
    assert set(accounts) == {"default", "acme"}
    assert accounts["acme"].token == "tok-acme"
    assert resolve_config(config_path=Path("/none.toml")).name == "default"
    assert resolve_config(account="acme", config_path=Path("/none.toml")).token == "tok-acme"


def test_accounts_from_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'default_account = "personal"\n'
        '[accounts.acme]\ntoken = "tok-acme"\n'
        '[accounts.personal]\ntoken = "tok-personal"\nbase_url = "https://x.test/api/v2/"\n'
    )
    accounts = resolve_accounts(cfg)
    assert set(accounts) == {"acme", "personal"}
    # default_account drives the no-account selection
    chosen = resolve_config(config_path=cfg)
    assert chosen.name == "personal"
    assert chosen.base_url == "https://x.test/api/v2/"


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    cfg = tmp_path / "config.toml"
    cfg.write_text('[accounts.acme]\ntoken = "from-file"\n')
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "from-env")
    assert resolve_accounts(cfg)["acme"].token == "from-env"


def test_unknown_account_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "tok")
    with pytest.raises(ConfigError, match="Unknown account"):
        resolve_config(account="nope", config_path=Path("/none.toml"))


def test_ambiguous_default_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "a")
    monkeypatch.setenv("HOLDED_TOKEN_PERSONAL", "b")
    with pytest.raises(ConfigError, match="Multiple accounts"):
        resolve_config(config_path=Path("/none.toml"))


def _stub_client(name: str) -> HoldedClient:
    transport = Transport("tok", base_url=BASE, client=httpx.Client(base_url=BASE))
    return HoldedClient(transport=transport, token="tok", account=name)


def test_multiclient_fans_out(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}contacts", json={"items": [{"id": "1"}]})
    httpx_mock.add_response(url=f"{BASE}contacts", json={"items": [{"id": "2"}]})
    multi = MultiClient({"acme": _stub_client("acme"), "personal": _stub_client("personal")})
    with multi:
        result = multi.contacts.list()
    assert set(result) == {"acme", "personal"}
    assert all("items" in r for r in result.values())


def test_multiclient_captures_per_account_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}contacts", json={"items": []})
    httpx_mock.add_response(url=f"{BASE}contacts", status_code=401, json={"message": "bad key"})
    multi = MultiClient({"good": _stub_client("good"), "bad": _stub_client("bad")})
    with multi:
        result = multi.call("contacts", "list")
    # One account failing must not abort the other.
    assert "items" in result["good"]
    assert "error" in result["bad"]


def test_multiclient_requires_at_least_one_account() -> None:
    with pytest.raises(ConfigError, match="at least one account"):
        MultiClient({})


def test_from_accounts_builds_every_configured_account(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "a")
    monkeypatch.setenv("HOLDED_TOKEN_PERSONAL", "b")
    with MultiClient.from_accounts(config_path=Path("/none.toml")) as multi:
        assert set(multi.accounts) == {"acme", "personal"}


def test_from_accounts_without_any_account_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    with pytest.raises(ConfigError, match="No Holded accounts"):
        MultiClient.from_accounts(config_path=Path("/none.toml"))


def test_from_accounts_rejects_unknown_names(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "a")
    with pytest.raises(ConfigError, match="Unknown account"):
        MultiClient.from_accounts(["nope"], config_path=Path("/none.toml"))


def test_from_accounts_selects_named_subset(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("HOLDED_TOKEN_ACME", "a")
    monkeypatch.setenv("HOLDED_TOKEN_PERSONAL", "b")
    with MultiClient.from_accounts(["acme"], config_path=Path("/none.toml")) as multi:
        assert multi.accounts == ["acme"]


def test_multiclient_request_fans_out(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}taxes", json={"items": [{"id": "t1"}]})
    httpx_mock.add_response(url=f"{BASE}taxes", json={"items": [{"id": "t2"}]})
    multi = MultiClient({"acme": _stub_client("acme"), "personal": _stub_client("personal")})
    with multi:
        result = multi.request("GET", "taxes")
    assert set(result) == {"acme", "personal"}


def test_multiclient_unknown_resource_raises() -> None:
    multi = MultiClient({"acme": _stub_client("acme")})
    with multi, pytest.raises(AttributeError):
        _ = multi.no_such_resource


def test_multiclient_unknown_operation_raises() -> None:
    # The shared proxy validates operations, so a bad op fails at attribute
    # access on the fan-out client just as it does on a single client.
    multi = MultiClient({"acme": _stub_client("acme")})
    with multi, pytest.raises(AttributeError):
        _ = multi.contacts.frobnicate
