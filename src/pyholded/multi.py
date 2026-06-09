"""Query several Holded accounts at once.

:class:`MultiClient` wraps one :class:`~pyholded.client.HoldedClient` per account
and fans a call out to all of them, returning a ``{account: result}`` mapping. A
failure on one account (auth, not-found, ...) is captured as ``{"error": ...}``
for that account instead of aborting the others.

    with MultiClient.from_accounts() as mc:
        per_account = mc.contacts.list(params={"limit": 5})
        # {"acme": {...}, "personal": {...}}
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .client import HoldedClient
from .config import resolve_accounts
from .exceptions import ConfigError, HoldedError
from .transport import DEFAULT_TIMEOUT


class MultiClient:
    """A fan-out client over several named accounts."""

    def __init__(self, clients: dict[str, HoldedClient]) -> None:
        if not clients:
            raise ConfigError("MultiClient requires at least one account.")
        self._clients = clients

    @classmethod
    def from_accounts(
        cls,
        names: list[str] | None = None,
        *,
        config_path: Path | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> MultiClient:
        """Build a client for the given account names (all configured if ``None``)."""
        accounts = resolve_accounts(config_path)
        if not accounts:
            raise ConfigError("No Holded accounts configured.")
        if names is not None:
            missing = [name for name in names if name not in accounts]
            if missing:
                raise ConfigError(
                    f"Unknown account(s) {sorted(missing)}; configured: "
                    f"{', '.join(sorted(accounts))}."
                )
            accounts = {name: accounts[name] for name in names}
        clients = {
            name: HoldedClient(
                config.token, account=name, base_url=config.base_url, timeout=timeout
            )
            for name, config in accounts.items()
        }
        return cls(clients)

    @property
    def accounts(self) -> list[str]:
        return list(self._clients)

    def call(self, resource: str, operation: str, **kwargs: Any) -> dict[str, Any]:
        """Invoke an operation on every account; map account -> result or error."""
        return self._fan_out(lambda client: client.call(resource, operation, **kwargs))

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Call an arbitrary endpoint on every account; map account -> result or error."""
        return self._fan_out(lambda client: client.request(method, path, **kwargs))

    def _fan_out(self, action: Callable[[HoldedClient], Any]) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, client in self._clients.items():
            try:
                results[name] = action(client)
            except HoldedError as exc:
                results[name] = {"error": str(exc)}
        return results

    def close(self) -> None:
        for client in self._clients.values():
            client.close()

    def __enter__(self) -> MultiClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __getattr__(self, name: str) -> _MultiResourceProxy:
        clients = self.__dict__.get("_clients", {})
        any_client = next(iter(clients.values()), None)
        if any_client is None or name not in any_client.resources:
            raise AttributeError(name)
        return _MultiResourceProxy(self, name)


class _MultiResourceProxy:
    def __init__(self, multi: MultiClient, resource: str) -> None:
        self._multi = multi
        self._resource = resource

    def __getattr__(self, name: str) -> _MultiOperationProxy:
        return _MultiOperationProxy(self._multi, self._resource, name)


class _MultiOperationProxy:
    def __init__(self, multi: MultiClient, resource: str, operation: str) -> None:
        self._multi = multi
        self._resource = resource
        self._operation = operation

    def __call__(
        self,
        *,
        params: dict[str, Any] | None = None,
        data: Any = None,
        paginate: bool = False,
        **path_params: str,
    ) -> dict[str, Any]:
        return self._multi.call(
            self._resource,
            self._operation,
            path_params=path_params,
            params=params,
            data=data,
            paginate=paginate,
        )
