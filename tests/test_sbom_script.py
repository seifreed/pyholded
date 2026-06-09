"""Regression tests for the SBOM generator script's guards."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import verify_sbom  # exposed on sys.path by tests/conftest.py

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "generate_sbom.py"
_SBOM = _ROOT / "sbom.cdx.json"


def test_missing_lockfile_fails_clearly(tmp_path: Path) -> None:
    # Regression: a missing lockfile used to yield a silent, empty-component SBOM
    # (the runtime-scope filter intersected an empty hash set). It must error.
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--lock", str(tmp_path / "absent.lock")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "lockfile not found" in result.stderr


def test_committed_sbom_signature_is_valid() -> None:
    # Regression: the committed SBOM must carry a valid embedded ES256 signature.
    sbom = json.loads(_SBOM.read_text(encoding="utf-8"))
    assert verify_sbom.verify(sbom) is True


def test_tampered_sbom_signature_is_rejected() -> None:
    sbom = json.loads(_SBOM.read_text(encoding="utf-8"))
    sbom["metadata"]["authors"] = [{"name": "tampered"}]
    assert verify_sbom.verify(sbom) is False
