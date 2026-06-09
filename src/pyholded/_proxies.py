"""Attribute-based dispatch for the registry-driven clients.

These proxies turn ``caller.<resource>.<operation>(**kwargs)`` into a single
:meth:`call` on whatever caller they are bound to. They hold no API knowledge
of their own — the endpoint registry is the single source of truth — and work
identically for the single-account :class:`~pyholded.client.HoldedClient` and
the fan-out :class:`~pyholded.multi.MultiClient`, since both expose the same
:meth:`call` contract.
"""

from __future__ import annotations

from typing import Any, Protocol

from ._registry import Endpoint, Resource


class _Caller(Protocol):
    """Anything the proxies can dispatch a registered operation to."""

    def call(
        self,
        resource: str,
        operation: str,
        *,
        path_params: dict[str, str] | None = ...,
        params: dict[str, Any] | None = ...,
        data: Any = ...,
        paginate: bool = ...,
    ) -> Any: ...


class ResourceProxy:
    """Attribute access wrapper for a single resource's operations."""

    def __init__(self, caller: _Caller, resource: Resource) -> None:
        self._caller = caller
        self._resource = resource

    def __getattr__(self, name: str) -> OperationProxy:
        endpoint = self._resource.get(name)
        if endpoint is None:
            raise AttributeError(name)
        return OperationProxy(self._caller, self._resource.name, endpoint)

    def __dir__(self) -> list[str]:
        return [*super().__dir__(), *self._resource.operations]


class OperationProxy:
    """A bound, callable API operation."""

    def __init__(self, caller: _Caller, resource: str, endpoint: Endpoint) -> None:
        self._caller = caller
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
        return self._caller.call(
            self._resource,
            self._endpoint.name,
            path_params=path_params,
            params=params,
            data=data,
            paginate=paginate,
        )
