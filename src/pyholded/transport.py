"""Low-level HTTP transport for the Holded API (v2).

Wraps :mod:`httpx` with Holded v2 ``Authorization: Bearer`` authentication,
JSON (de)serialization and error mapping. The high-level client builds on top
of this; nothing here knows about specific endpoints.
"""

from __future__ import annotations

from typing import Any

import httpx

from .exceptions import (
    APIError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
)

DEFAULT_TIMEOUT = 30.0
USER_AGENT = "pyholded"

_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_HTTP_NOT_FOUND = 404
_HTTP_TOO_MANY_REQUESTS = 429


class Transport:
    """Thin authenticated wrapper around :class:`httpx.Client`."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)
        self._client.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            }
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        binary: bool = False,
    ) -> Any:
        """Send a request and return the decoded body (or raw bytes if ``binary``)."""
        response = self._client.request(
            method.upper(),
            path,
            params=_clean_params(params),
            json=json,
        )
        self._raise_for_status(response)
        if binary:
            return response.content
        if not response.content:
            return None
        try:
            data = response.json()
        except ValueError:
            return response.text
        _raise_for_envelope_error(data, response)
        return data

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        payload = _safe_json(response)
        message = _error_message(response, payload)
        status = response.status_code
        if status in (_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN):
            raise AuthenticationError(message, status_code=status, payload=payload)
        if status == _HTTP_NOT_FOUND:
            raise NotFoundError(message, status_code=status, payload=payload)
        if status == _HTTP_TOO_MANY_REQUESTS:
            raise RateLimitError(message, status_code=status, payload=payload)
        raise APIError(message, status_code=status, payload=payload)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Transport:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    return {key: value for key, value in params.items() if value is not None}


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text or None


def _raise_for_envelope_error(payload: Any, response: httpx.Response) -> None:
    """Raise on Holded's ``{"status": 0, "info": ...}`` error body returned with HTTP 200.

    Some Holded endpoints (e.g. a delete the key is not allowed to perform) reply
    200 with this failure envelope instead of a 4xx, which would otherwise be
    mistaken for success.
    """
    if isinstance(payload, dict) and payload.get("status") == 0 and "info" in payload:
        info = payload.get("info")
        message = str(info) if info else "Holded API request failed"
        raise APIError(message, status_code=response.status_code, payload=payload)


def _error_message(response: httpx.Response, payload: Any) -> str:
    # Covers Holded's "message"/"error"/"info" bodies and RFC 7807 problem+json
    # ("detail"/"title"), which the v2 API returns for 4xx responses.
    if isinstance(payload, dict):
        for key in ("message", "error", "info", "detail", "title"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return f"Holded API returned HTTP {response.status_code}"
