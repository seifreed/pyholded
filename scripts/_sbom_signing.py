"""Shared ECDSA P-256 (ES256) signing primitives for the SBOM scripts.

Signing (:mod:`generate_sbom`) and verification (:mod:`verify_sbom`) must agree
byte-for-byte on the canonical payload and on the base64url encoding. Keeping
those here makes the contract a single source of truth instead of two copies
that can silently drift apart and break every signature.
"""

from __future__ import annotations

import base64
import json
from typing import Any

COORD_BYTES = 32  # P-256 coordinate / signature-half size


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def canonical_bytes(sbom: dict[str, Any]) -> bytes:
    """Deterministic JSON bytes of the SBOM with the signature block excluded."""
    payload = {key: value for key, value in sbom.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
