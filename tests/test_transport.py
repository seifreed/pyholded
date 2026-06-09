"""Transport-layer tests covering status mapping, body decoding and lifecycle."""

from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from pyholded.exceptions import APIError, RateLimitError
from pyholded.transport import Transport

BASE = "https://api.holded.test/api/v2/"


def _transport_with_mock() -> Transport:
    return Transport("tkn", base_url=BASE, client=httpx.Client(base_url=BASE))


def test_empty_response_body_returns_none(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}ping", status_code=204)
    with _transport_with_mock() as transport:
        assert transport.request("GET", "ping") is None


def test_non_json_body_returns_text(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}ping", content=b"pong", headers={"content-type": "text/plain"}
    )
    with _transport_with_mock() as transport:
        assert transport.request("GET", "ping") == "pong"


def test_rate_limit_status_maps_to_rate_limit_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}ping", status_code=429, json={"message": "slow down"})
    with _transport_with_mock() as transport, pytest.raises(RateLimitError, match="slow down"):
        transport.request("GET", "ping")


def test_server_error_without_message_uses_status_fallback(httpx_mock: HTTPXMock) -> None:
    # A 5xx with no recognised message field falls back to a status-coded message.
    httpx_mock.add_response(url=f"{BASE}ping", status_code=500, json={})
    with _transport_with_mock() as transport, pytest.raises(APIError, match="HTTP 500"):
        transport.request("GET", "ping")


def test_error_body_that_is_not_json_is_surfaced(httpx_mock: HTTPXMock) -> None:
    # Regression: a non-JSON error body must not blow up the error decoder.
    httpx_mock.add_response(
        url=f"{BASE}ping",
        status_code=500,
        content=b"upstream exploded",
        headers={"content-type": "text/plain"},
    )
    with _transport_with_mock() as transport, pytest.raises(APIError, match="HTTP 500"):
        transport.request("GET", "ping")


def test_owned_client_is_closed_via_context_manager() -> None:
    # When no client is injected, the transport owns and closes its httpx client.
    transport = Transport("tkn", base_url=BASE)
    with transport as same:
        assert same is transport
    # Closing again must be a safe no-op.
    transport.close()
