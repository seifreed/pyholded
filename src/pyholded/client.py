"""High-level Holded client.

Resources and their operations are exposed as attributes generated from the
endpoint registry::

    client = HoldedClient()                       # token from env or config file
    invoices = client.documents.list(docType="invoice")
    contact = client.contacts.get(contactId="...")

Any endpoint can also be reached generically via :meth:`HoldedClient.request`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._registry import Endpoint, Resource, build_index, render_path
from .config import resolve_config
from .endpoints import REGISTRY
from .exceptions import EndpointNotFoundError
from .transport import DEFAULT_TIMEOUT, Transport


class HoldedClient:
    """Entry point to the Holded API."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str | None = None,
        config_path: Path | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: Transport | None = None,
    ) -> None:
        config = resolve_config(token, base_url=base_url, config_path=config_path)
        self._transport = transport or Transport(
            config.token, base_url=config.base_url, timeout=timeout
        )
        self._resources = build_index(REGISTRY)

    @property
    def resources(self) -> dict[str, Resource]:
        """The full resource index, keyed by resource name."""
        return self._resources

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        binary: bool = False,
    ) -> Any:
        """Call an arbitrary endpoint (escape hatch for anything not modelled)."""
        return self._transport.request(method, path, params=params, json=json, binary=binary)

    def call(
        self,
        resource: str,
        operation: str,
        *,
        path_params: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        data: Any = None,
        paginate: bool = False,
    ) -> Any:
        """Invoke a registered operation by name (used by the CLI).

        When ``paginate`` is true on a GET that returns a cursor-paginated
        ``{items, cursor, has_more}`` body, every page is fetched and the
        merged ``items`` list is returned.
        """
        endpoint = self._lookup(resource, operation)
        path = render_path(endpoint.path, path_params or {})
        if paginate and endpoint.method == "GET" and not endpoint.binary:
            return self._paginate(path, params)
        return self._invoke(endpoint, path, params, data)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> HoldedClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __getattr__(self, name: str) -> ResourceProxy:
        # Only reached for attributes not found normally.
        resources = self.__dict__.get("_resources", {})
        resource = resources.get(name)
        if resource is None:
            raise AttributeError(name)
        return ResourceProxy(self, resource)

    def __dir__(self) -> list[str]:
        return [*super().__dir__(), *self._resources]

    def _lookup(self, resource: str, operation: str) -> Endpoint:
        res = self._resources.get(resource)
        if res is None:
            raise EndpointNotFoundError(f"Unknown resource: {resource}")
        endpoint = res.get(operation)
        if endpoint is None:
            raise EndpointNotFoundError(f"Unknown operation '{operation}' on resource '{resource}'")
        return endpoint

    def _invoke(
        self,
        endpoint: Endpoint,
        path: str,
        params: dict[str, Any] | None,
        data: Any,
    ) -> Any:
        body = data if endpoint.has_body else None
        return self._transport.request(
            endpoint.method,
            path,
            params=params,
            json=body,
            binary=endpoint.binary,
        )

    def _paginate(self, path: str, params: dict[str, Any] | None) -> list[Any]:
        items: list[Any] = []
        query = dict(params or {})
        seen_cursors: set[str] = set()
        while True:
            page = self._transport.request("GET", path, params=query)
            if not isinstance(page, dict) or "items" not in page:
                # Not a paginated shape; hand the raw body back as a single item.
                return [page]
            items.extend(page["items"])
            cursor = page.get("cursor")
            if not page.get("has_more") or not cursor:
                return items
            # Defend against an API that keeps returning the same cursor.
            if cursor in seen_cursors:
                return items
            seen_cursors.add(cursor)
            query["cursor"] = cursor


class ResourceProxy:
    """Attribute access wrapper for a single resource's operations."""

    def __init__(self, client: HoldedClient, resource: Resource) -> None:
        self._client = client
        self._resource = resource

    def __getattr__(self, name: str) -> OperationProxy:
        endpoint = self._resource.get(name)
        if endpoint is None:
            raise AttributeError(name)
        return OperationProxy(self._client, self._resource.name, endpoint)

    def __dir__(self) -> list[str]:
        return [*super().__dir__(), *self._resource.operations]


class OperationProxy:
    """A bound, callable API operation."""

    def __init__(self, client: HoldedClient, resource: str, endpoint: Endpoint) -> None:
        self._client = client
        self._resource = resource
        self._endpoint = endpoint

    def __call__(
        self,
        *,
        params: dict[str, Any] | None = None,
        data: Any = None,
        paginate: bool = False,
        **path_params: str,
    ) -> Any:
        return self._client.call(
            self._resource,
            self._endpoint.name,
            path_params=path_params,
            params=params,
            data=data,
            paginate=paginate,
        )
