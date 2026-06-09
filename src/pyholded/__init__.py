"""pyholded — a modular Python client and CLI for the complete Holded API."""

from __future__ import annotations

from importlib import metadata

from ._registry import Endpoint, Resource
from .client import HoldedClient
from .config import Config, resolve_config, resolve_token
from .endpoints import REGISTRY
from .exceptions import (
    APIError,
    AuthenticationError,
    ConfigError,
    EndpointNotFoundError,
    HoldedError,
    NotFoundError,
    RateLimitError,
)
from .output import OutputFormat, render, to_json, to_toon


def _detect_version() -> str:
    try:
        return metadata.version("pyholded")
    except metadata.PackageNotFoundError:
        return "0.0.0"


__version__ = _detect_version()

__all__ = [
    "REGISTRY",
    "APIError",
    "AuthenticationError",
    "Config",
    "ConfigError",
    "Endpoint",
    "EndpointNotFoundError",
    "HoldedClient",
    "HoldedError",
    "NotFoundError",
    "OutputFormat",
    "RateLimitError",
    "Resource",
    "__version__",
    "render",
    "resolve_config",
    "resolve_token",
    "to_json",
    "to_toon",
]
