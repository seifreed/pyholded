"""Configuration and API-token resolution.

The token is resolved from, in order of precedence:

1. An explicit value passed to :func:`resolve_token` (e.g. the CLI ``--token`` flag).
2. The ``HOLDED_API_KEY`` environment variable (``HOLDED_TOKEN`` is also accepted).
3. A config file (TOML), located via ``--config``, the ``HOLDED_CONFIG`` environment
   variable, or the default ``$XDG_CONFIG_HOME/pyholded/config.toml``.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigError

ENV_TOKEN_KEYS = ("HOLDED_TOKEN", "HOLDED_API_KEY")
ENV_CONFIG_KEY = "HOLDED_CONFIG"
DEFAULT_BASE_URL = "https://api.holded.com/api/v2/"


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved client configuration."""

    token: str
    base_url: str = DEFAULT_BASE_URL


def default_config_path() -> Path:
    """Return the default config file path following the XDG base-dir spec."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "pyholded" / "config.toml"


def load_config_file(path: Path) -> dict[str, str]:
    """Read a TOML config file and return its flat ``[holded]`` section.

    The file may put values either at the top level or under a ``[holded]`` table::

        [holded]
        token = "abc123"
        base_url = "https://api.holded.com/api/"
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    parsed = tomllib.loads(raw.decode("utf-8"))
    section = parsed.get("holded", parsed)
    if not isinstance(section, dict):
        raise ConfigError(f"Invalid config file structure in {path}")
    return {str(k): str(v) for k, v in section.items() if isinstance(v, (str, int, float))}


def resolve_token(
    explicit: str | None = None,
    *,
    config_path: Path | None = None,
) -> str:
    """Resolve the API token, raising :class:`ConfigError` if none is found."""
    return resolve_config(explicit, config_path=config_path).token


def resolve_config(
    explicit_token: str | None = None,
    *,
    base_url: str | None = None,
    config_path: Path | None = None,
) -> Config:
    """Resolve the full client configuration (token + base URL)."""
    file_values: dict[str, str] = {}
    path = config_path or _config_path_from_env()
    if path is not None and path.exists():
        file_values = load_config_file(path)

    token = explicit_token or _token_from_env() or file_values.get("token")
    if not token:
        raise ConfigError(
            "No Holded API token found. Provide --token, set the HOLDED_API_KEY "
            "environment variable, or add 'token' to your config file."
        )

    resolved_base = base_url or file_values.get("base_url") or DEFAULT_BASE_URL
    return Config(token=token, base_url=resolved_base)


def _token_from_env() -> str | None:
    for key in ENV_TOKEN_KEYS:
        value = os.environ.get(key)
        if value:
            return value
    return None


def _config_path_from_env() -> Path | None:
    env_path = os.environ.get(ENV_CONFIG_KEY)
    if env_path:
        return Path(env_path)
    default = default_config_path()
    return default if default.exists() else None
