"""Regression tests for the SBOM generator script's guards."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_sbom.py"


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
