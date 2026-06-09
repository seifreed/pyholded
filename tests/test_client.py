"""Client/transport tests against a stubbed HTTP layer (Holded API v2)."""

from __future__ import annotations

import json

import httpx
import pytest
from pytest_httpx import HTTPXMock

from pyholded import HoldedClient
from pyholded.exceptions import AuthenticationError, EndpointNotFoundError, NotFoundError
from pyholded.transport import Transport

BASE = "https://api.holded.test/api/v2/"


def _client() -> HoldedClient:
    transport = Transport("tkn", base_url=BASE, client=httpx.Client(base_url=BASE))
    return HoldedClient(transport=transport, token="tkn")


def test_bearer_auth_header(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}contacts", json={"items": []})
    with _client() as client:
        client.contacts.list()
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Authorization"] == "Bearer tkn"


def test_get_with_path_param(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}invoices/abc", json={"id": "abc"})
    with _client() as client:
        assert client.invoices.get(id="abc") == {"id": "abc"}


def test_create_sends_body(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}contacts", method="POST", json={"id": "new"})
    with _client() as client:
        client.contacts.create(data={"name": "ACME"})
    request = httpx_mock.get_request()
    assert request is not None
    assert json.loads(request.read()) == {"name": "ACME"}


def test_pagination_follows_cursor(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}contacts?limit=2",
        json={"items": [{"id": "1"}, {"id": "2"}], "cursor": "c1", "has_more": True},
    )
    httpx_mock.add_response(
        url=f"{BASE}contacts?limit=2&cursor=c1",
        json={"items": [{"id": "3"}], "cursor": None, "has_more": False},
    )
    with _client() as client:
        items = client.contacts.list(params={"limit": 2}, paginate=True)
    assert [i["id"] for i in items] == ["1", "2", "3"]


def test_pagination_stops_on_repeated_cursor(httpx_mock: HTTPXMock) -> None:
    # Regression: a stuck cursor (has_more stays true, cursor never changes)
    # must not loop forever.
    httpx_mock.add_response(
        url=f"{BASE}contacts?limit=1",
        json={"items": [{"id": "1"}], "cursor": "c1", "has_more": True},
    )
    httpx_mock.add_response(
        url=f"{BASE}contacts?limit=1&cursor=c1",
        json={"items": [{"id": "2"}], "cursor": "c1", "has_more": True},
    )
    with _client() as client:
        items = client.contacts.list(params={"limit": 1}, paginate=True)
    assert [i["id"] for i in items] == ["1", "2"]


def test_binary_action(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}invoices/abc/pdf", content=b"%PDF-1.4")
    with _client() as client:
        assert client.invoices.getPdf(id="abc") == b"%PDF-1.4"


def test_authentication_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=401, json={"message": "bad token"})
    with _client() as client, pytest.raises(AuthenticationError):
        client.contacts.list()


def test_not_found_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=404, json={"message": "nope"})
    with _client() as client, pytest.raises(NotFoundError):
        client.contacts.get(id="x")


def test_problem_json_error_message(httpx_mock: HTTPXMock) -> None:
    # Regression: Holded v2 returns RFC 7807 problem+json; surface its "detail".
    httpx_mock.add_response(
        status_code=404,
        json={
            "type": "https://api.holded.com/problems/not-found",
            "title": "Not found",
            "detail": "Not Found",
            "status": 404,
        },
    )
    with _client() as client, pytest.raises(NotFoundError) as excinfo:
        client.contacts.get(id="x")
    assert str(excinfo.value) == "Not Found"


def test_unknown_operation() -> None:
    with _client() as client, pytest.raises(EndpointNotFoundError):
        client.call("contacts", "frobnicate")


def test_misplaced_query_kwarg_raises() -> None:
    # Regression: a query param passed as a kwarg used to be silently dropped
    # (e.g. list(limit=5) sent no query at all). It must now raise, not no-op.
    with _client() as client, pytest.raises(TypeError, match="limit"):
        client.contacts.list(limit="5")


def test_generic_request(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}taxes", json={"items": [{"id": "t1"}]})
    with _client() as client:
        assert client.request("GET", "taxes") == {"items": [{"id": "t1"}]}
