"""Package-level surface tests: version detection and re-exports."""

from __future__ import annotations

from importlib import metadata

import pytest

import pyholded


def test_detect_version_matches_installed_metadata() -> None:
    assert pyholded._detect_version() == pyholded.__version__


def test_detect_version_falls_back_when_package_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: a source checkout with no installed distribution must not crash
    # on import; it falls back to a sentinel version instead.
    def _raise(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr("pyholded.metadata.version", _raise)
    assert pyholded._detect_version() == "0.0.0"
