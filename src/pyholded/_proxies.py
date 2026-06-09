"""Attribute-based dispatch for the registry-driven client.

These proxies turn ``client.<resource>.<operation>(**kwargs)`` into a single
:meth:`HoldedClient.call`. They hold no API knowledge of their own — the
endpoint registry is the single source of truth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._registry import Endpoint, Resource

if TYPE_CHECKING:
    from .client import HoldedClient


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
