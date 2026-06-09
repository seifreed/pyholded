"""Registry integrity tests."""

from __future__ import annotations

import pytest

from pyholded._registry import build_index, render_path
from pyholded.endpoints import REGISTRY

VALID_METHODS = {"GET", "POST", "PUT", "DELETE"}


def test_resource_names_unique() -> None:
    index = build_index(REGISTRY)
    assert len(index) == len(REGISTRY)


def test_endpoints_are_well_formed() -> None:
    for resource in REGISTRY:
        assert resource.endpoints, f"{resource.name} has no endpoints"
        for endpoint in resource.endpoints:
            assert endpoint.method in VALID_METHODS
            assert not endpoint.path.startswith("/")
            if endpoint.method in {"GET", "DELETE"}:
                assert not endpoint.has_body, f"{resource.name}.{endpoint.name}"


def test_operation_names_unique_per_resource() -> None:
    for resource in REGISTRY:
        names = [ep.name for ep in resource.endpoints]
        assert len(names) == len(set(names)), resource.name


def test_render_path_substitutes() -> None:
    rendered = render_path("invoices/{id}/pdf", {"id": "abc"})
    assert rendered == "invoices/abc/pdf"


def test_render_path_missing_param() -> None:
    with pytest.raises(KeyError):
        render_path("invoices/{id}", {})


def test_render_path_encodes_special_chars() -> None:
    # Regression: an id with /, # or ? must not corrupt the path/query.
    assert render_path("contacts/{id}", {"id": "a/b#c?d"}) == "contacts/a%2Fb%23c%3Fd"
    # Plain hex ids (the real-world case) are unchanged.
    assert render_path("contacts/{id}", {"id": "5eaa9a4e"}) == "contacts/5eaa9a4e"
