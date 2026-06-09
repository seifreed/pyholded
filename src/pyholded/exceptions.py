"""Exception hierarchy for the Holded client."""

from __future__ import annotations

from typing import Any


class HoldedError(Exception):
    """Base class for every error raised by this library."""


class ConfigError(HoldedError):
    """Raised when the API token or configuration cannot be resolved."""


class APIError(HoldedError):
    """Raised when the Holded API returns an unsuccessful HTTP status.

    Attributes:
        status_code: The HTTP status code returned by the API.
        payload: The decoded response body, when available.
    """

    def __init__(self, message: str, *, status_code: int, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class AuthenticationError(APIError):
    """Raised on HTTP 401/403 responses (missing or invalid API key)."""


class NotFoundError(APIError):
    """Raised on HTTP 404 responses."""


class RateLimitError(APIError):
    """Raised on HTTP 429 responses."""


class EndpointNotFoundError(HoldedError):
    """Raised when an unknown resource or operation is requested."""
