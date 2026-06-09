#!/usr/bin/env python3
"""Verify the embedded ECDSA P-256 (ES256) JSF signature of a CycloneDX SBOM.

The public key travels with the document (``signature.publicKey`` JWK), so no
external key material is needed. Exits non-zero if the signature is invalid.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from _sbom_signing import COORD_BYTES, b64url_decode, canonical_bytes
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


def verify(sbom: dict[str, Any]) -> bool:
    """Return True if the SBOM's embedded signature matches its canonical bytes."""
    signature = sbom.get("signature")
    if not isinstance(signature, dict):
        raise ValueError("SBOM has no signature block")
    payload = canonical_bytes(sbom)
    jwk = signature["publicKey"]
    public_key = ec.EllipticCurvePublicNumbers(
        int.from_bytes(b64url_decode(jwk["x"]), "big"),
        int.from_bytes(b64url_decode(jwk["y"]), "big"),
        ec.SECP256R1(),
    ).public_key()
    raw = b64url_decode(signature["value"])
    der = encode_dss_signature(
        int.from_bytes(raw[:COORD_BYTES], "big"), int.from_bytes(raw[COORD_BYTES:], "big")
    )
    try:
        public_key.verify(der, payload, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    path = Path(args[0]) if args else Path("sbom.cdx.json")
    sbom = json.loads(path.read_text(encoding="utf-8"))
    if verify(sbom):
        print(f"{path}: signature valid")
        return 0
    print(f"{path}: signature INVALID", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
