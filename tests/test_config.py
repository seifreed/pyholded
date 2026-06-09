"""Token/config resolution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyholded.config import DEFAULT_BASE_URL, resolve_config, resolve_token
from pyholded.exceptions import ConfigError


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
