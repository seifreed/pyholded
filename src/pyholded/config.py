"""Configuration and API-token resolution, with multi-account support.

A single account's token is resolved from, in order of precedence:

1. An explicit value (e.g. the CLI ``--token`` flag).
2. Environment variables — ``HOLDED_TOKEN``/``HOLDED_API_KEY`` for the ``default``
   account, and ``HOLDED_TOKEN_<NAME>`` for a named account (e.g. ``HOLDED_TOKEN_ACME``).
3. A TOML config file (``--config``, ``HOLDED_CONFIG``, or
   ``$XDG_CONFIG_HOME/pyholded/config.toml``) with per-account tables::

       default_account = "acme"        # optional

       [accounts.acme]
       token = "pat_xxx"
       # base_url = "..."              # optional, per account

       [accounts.personal]
       token = "pat_yyy"

   A legacy top-level (or ``[holded]``) ``token`` is read as the ``default`` account.

Environment accounts override file accounts with the same name.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .exceptions import ConfigError

ENV_TOKEN_KEYS = ("HOLDED_TOKEN", "HOLDED_API_KEY")
ENV_ACCOUNT_PREFIX = "HOLDED_TOKEN_"
ENV_CONFIG_KEY = "HOLDED_CONFIG"
DEFAULT_BASE_URL = "https://api.holded.com/api/v2/"
DEFAULT_ACCOUNT = "default"


@dataclass(frozen=True, slots=True)
class Config:
    """Resolved configuration for a single account."""

    token: str
    base_url: str = DEFAULT_BASE_URL
    name: str = DEFAULT_ACCOUNT


def default_config_path() -> Path:
    """Return the default config file path following the XDG base-dir spec."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "pyholded" / "config.toml"


def resolve_token(explicit: str | None = None, *, config_path: Path | None = None) -> str:
    """Resolve the default account's API token, raising :class:`ConfigError` if none."""
    return resolve_config(explicit, config_path=config_path).token


def resolve_config(
    explicit_token: str | None = None,
    *,
    base_url: str | None = None,
    config_path: Path | None = None,
    account: str | None = None,
) -> Config:
    """Resolve a single account's configuration (token + base URL).

    With ``account`` set, that named account is required. Otherwise the default
    account is chosen (``default_account``, then ``default``, then the sole
    account if exactly one is configured).
    """
    if explicit_token:
        token = explicit_token.strip()
        if not token:
            raise ConfigError("Empty API token provided.")
        return Config(
            token=token, base_url=base_url or DEFAULT_BASE_URL, name=account or DEFAULT_ACCOUNT
        )

    accounts, configured_default = _load_accounts(config_path)
    if not accounts:
        raise ConfigError(
            "No Holded API token found. Provide --token, set the HOLDED_TOKEN "
            "environment variable, or add an account to your config file."
        )

    if account is not None:
        if account not in accounts:
            raise ConfigError(
                f"Unknown account '{account}'. Configured accounts: "
                f"{', '.join(sorted(accounts))}."
            )
        chosen = accounts[account]
    else:
        chosen = accounts[_pick_default(accounts, configured_default)]

    return replace(chosen, base_url=base_url) if base_url else chosen


def resolve_accounts(config_path: Path | None = None) -> dict[str, Config]:
    """Return every configured account, keyed by name (env + config file)."""
    return _load_accounts(config_path)[0]


def _pick_default(accounts: dict[str, Config], configured_default: str | None) -> str:
    if configured_default and configured_default in accounts:
        return configured_default
    if DEFAULT_ACCOUNT in accounts:
        return DEFAULT_ACCOUNT
    if len(accounts) == 1:
        return next(iter(accounts))
    raise ConfigError(
        f"Multiple accounts configured ({', '.join(sorted(accounts))}); choose one "
        "with --account / account=, or set default_account in the config file."
    )


def _load_accounts(config_path: Path | None) -> tuple[dict[str, Config], str | None]:
    parsed = _read_config_file(config_path)
    accounts = _accounts_from_file(parsed)
    accounts.update(_accounts_from_env())  # env overrides file by name
    default = parsed.get("default_account")
    return accounts, str(default) if isinstance(default, str) else None


def _read_config_file(config_path: Path | None) -> dict[str, Any]:
    path = config_path or _config_path_from_env()
    if path is None or not path.exists():
        return {}
    parsed = tomllib.loads(path.read_bytes().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ConfigError(f"Invalid config file structure in {path}")
    return parsed


def _accounts_from_file(parsed: dict[str, Any]) -> dict[str, Config]:
    accounts: dict[str, Config] = {}
    section = parsed.get("accounts")
    if isinstance(section, dict):
        for name, table in section.items():
            account = _account_from_table(str(name), table)
            if account is not None:
                accounts[account.name] = account
    legacy = parsed.get("holded", parsed)
    legacy_account = _account_from_table(DEFAULT_ACCOUNT, legacy)
    if legacy_account is not None:
        accounts.setdefault(DEFAULT_ACCOUNT, legacy_account)
    return accounts


def _account_from_table(name: str, table: Any) -> Config | None:
    if not isinstance(table, dict):
        return None
    token = table.get("token")
    if not isinstance(token, str) or not token.strip():
        return None
    base_url = table.get("base_url")
    return Config(
        token=token.strip(),
        base_url=str(base_url) if isinstance(base_url, str) else DEFAULT_BASE_URL,
        name=name,
    )


def _accounts_from_env() -> dict[str, Config]:
    accounts: dict[str, Config] = {}
    default_token = _token_from_env()
    if default_token:
        accounts[DEFAULT_ACCOUNT] = Config(token=default_token.strip(), name=DEFAULT_ACCOUNT)
    for key, value in os.environ.items():
        if not key.startswith(ENV_ACCOUNT_PREFIX) or not value.strip():
            continue
        name = key[len(ENV_ACCOUNT_PREFIX) :].lower()
        if name:
            accounts[name] = Config(token=value.strip(), name=name)
    return accounts


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
