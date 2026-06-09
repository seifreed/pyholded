"""Declarative model for the Holded API surface.

Every endpoint is described once, as data. Both the high-level client
(:mod:`pyholded.client`) and the command-line interface (:mod:`pyholded.cli`)
are generated from this registry, so the API surface has a single source of truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PLACEHOLDER = re.compile(r"\{([^}]+)\}")

HTTPMethod = str  # one of GET, POST, PUT, DELETE


@dataclass(frozen=True, slots=True)
class Endpoint:
    """A single API operation within a resource."""

    name: str
    method: HTTPMethod
    path: str
    description: str = ""
    query_params: tuple[str, ...] = ()
    has_body: bool = False
    binary: bool = False

    @property
    def path_params(self) -> tuple[str, ...]:
        """Names of the ``{placeholder}`` segments in :attr:`path`."""
        return tuple(_PLACEHOLDER.findall(self.path))


@dataclass(frozen=True, slots=True)
class Resource:
    """A named group of related endpoints belonging to one API module."""

    module: str
    name: str
    description: str
    endpoints: tuple[Endpoint, ...]
    operations: dict[str, Endpoint] = field(init=False, default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        # frozen dataclass: populate the lookup table without reassigning the field.
        self.operations.update({ep.name: ep for ep in self.endpoints})

    def get(self, operation: str) -> Endpoint | None:
        return self.operations.get(operation)


def build_index(resources: tuple[Resource, ...]) -> dict[str, Resource]:
    """Index resources by name, rejecting duplicates."""
    index: dict[str, Resource] = {}
    for resource in resources:
        if resource.name in index:
            raise ValueError(f"Duplicate resource name: {resource.name}")
        index[resource.name] = resource
    return index


def render_path(template: str, path_params: dict[str, str]) -> str:
    """Substitute ``{placeholders}`` in ``template`` with ``path_params`` values."""
    missing: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        value = path_params.get(key)
        if value is None or value == "":
            missing.append(key)
            return ""
        return str(value)

    rendered = _PLACEHOLDER.sub(_sub, template)
    if missing:
        raise KeyError(f"Missing path parameter(s): {', '.join(missing)}")
    return rendered.lstrip("/")
