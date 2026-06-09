"""Token/config resolution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyholded.config import (
    DEFAULT_BASE_URL,
    default_config_path,
    resolve_accounts,
    resolve_config,
    resolve_token,
)
from pyholded.exceptions import ConfigError


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("HOLDED_TOKEN", "HOLDED_API_KEY", "HOLDED_CONFIG", "HOLDED_TOKEN_ACME"):
        monkeypatch.delenv(key, raising=False)


def test_explicit_token_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLDED_API_KEY", "from-env")
    assert resolve_token("explicit") == "explicit"


def test_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLDED_TOKEN", raising=False)
    monkeypatch.setenv("HOLDED_API_KEY", "env-key")
    config = resolve_config(config_path=Path("/does/not/exist.toml"))
    assert config.token == "env-key"
    assert config.base_url == DEFAULT_BASE_URL


def test_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLDED_API_KEY", raising=False)
    monkeypatch.delenv("HOLDED_TOKEN", raising=False)
    cfg = tmp_path / "config.toml"
    cfg.write_text('[holded]\ntoken = "file-key"\nbase_url = "https://example.test/api/"\n')
    config = resolve_config(config_path=cfg)
    assert config.token == "file-key"
    assert config.base_url == "https://example.test/api/"


def test_missing_token_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLDED_API_KEY", raising=False)
    monkeypatch.delenv("HOLDED_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        resolve_config(config_path=tmp_path / "absent.toml")


def test_token_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: a token read from a file/env may carry a trailing newline,
    # which would otherwise corrupt the Authorization header.
    monkeypatch.delenv("HOLDED_API_KEY", raising=False)
    monkeypatch.setenv("HOLDED_TOKEN", "pat_abc\n")
    assert resolve_config(config_path=Path("/none.toml")).token == "pat_abc"


def test_whitespace_only_token_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOLDED_API_KEY", raising=False)
    monkeypatch.delenv("HOLDED_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        resolve_config("   ", config_path=Path("/none.toml"))


def test_default_config_path_honours_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg-home")
    assert default_config_path() == Path("/tmp/xdg-home/pyholded/config.toml")


def test_default_config_path_falls_back_to_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert default_config_path() == Path.home() / ".config" / "pyholded" / "config.toml"


def test_sole_named_account_is_the_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    cfg = tmp_path / "config.toml"
    cfg.write_text('[accounts.acme]\ntoken = "tok-acme"\n')
    chosen = resolve_config(config_path=cfg)
    assert chosen.name == "acme"


def test_non_table_account_entry_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_env(monkeypatch)
    cfg = tmp_path / "config.toml"
    cfg.write_text('[accounts]\nacme = "not-a-table"\n')
    assert resolve_accounts(cfg) == {}


def test_invalid_config_structure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Defensive guard: a parsed config that is not a table is rejected loudly.
    _clear_env(monkeypatch)
    cfg = tmp_path / "config.toml"
    cfg.write_text("answer = 42\n")
    monkeypatch.setattr("pyholded.config.tomllib.loads", lambda _text: [1, 2, 3])
    with pytest.raises(ConfigError, match="Invalid config file structure"):
        resolve_accounts(cfg)


def test_config_path_resolved_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    cfg = tmp_path / "config.toml"
    cfg.write_text('[accounts.acme]\ntoken = "tok-acme"\n')
    monkeypatch.setenv("HOLDED_CONFIG", str(cfg))
    assert "acme" in resolve_accounts()


def test_config_path_env_absent_yields_no_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert resolve_accounts() == {}


def test_env_account_with_empty_name_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    # A bare "HOLDED_TOKEN_" prefix yields an empty account name and is skipped.
    _clear_env(monkeypatch)
    monkeypatch.setenv("HOLDED_TOKEN_", "stray")
    assert resolve_accounts(Path("/none.toml")) == {}
