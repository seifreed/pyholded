#!/usr/bin/env python3
"""Generate an enriched CycloneDX SBOM for pyholded.

Pipeline (all data is real — nothing is fabricated):

1. ``cyclonedx-py environment`` produces the base SBOM from the installed venv
   (clean component set, purls, root component from pyproject.toml).
2. Real PyPI artifact SHA-256 hashes are read from ``requirements.lock`` (a
   ``uv pip compile --generate-hashes`` lockfile) and attached per component.
3. Per-component licenses and suppliers are filled from the installed package
   metadata (``importlib.metadata``).
4. The dependency graph is built from each distribution's declared requirements.
5. Document-level metadata (authors, supplier, lifecycle, BOM data license) is set.

Usage:
    python scripts/generate_sbom.py [--venv venv] [--lock requirements.lock] \
        [--pyproject pyproject.toml] [--output sbom.cdx.json]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any

from _sbom_signing import COORD_BYTES, b64url_encode, canonical_bytes
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

_MAX_LICENSE_LEN = 64
_HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})")
_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", re.MULTILINE)
_SUPPLIER = {"name": "Marc Rivero López", "url": ["https://github.com/seifreed/pyholded"]}

# Known SPDX licenses for runtime dependencies whose installed metadata omits one.
_LICENSE_OVERRIDES = {"toons": "Apache-2.0"}

# Map common Trove license classifiers to SPDX identifiers.
_CLASSIFIER_SPDX = {
    "Apache Software License": "Apache-2.0",
    "MIT License": "MIT",
    "BSD License": "BSD-3-Clause",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "ISC License (ISCL)": "ISC",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
}
_SPDX_IDS = set(_CLASSIFIER_SPDX.values()) | {
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "MIT",
    "MPL-2.0",
    "PSF-2.0",
    "Python-2.0",
    "ISC",
    "CC0-1.0",
}


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock_hashes(lock_path: Path) -> dict[str, list[str]]:
    """Map normalized package name -> list of real SHA-256 artifact hashes."""
    hashes: dict[str, list[str]] = {}
    current: str | None = None
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        name_match = _NAME_RE.match(line.strip())
        if name_match:
            current = _normalize(name_match.group(1))
            hashes.setdefault(current, [])
        if current:
            hashes[current].extend(_HASH_RE.findall(line))
    return {name: values for name, values in hashes.items() if values}


def _dist_license(dist_name: str) -> str | None:
    """Return a license string for a distribution, preferring an SPDX identifier."""
    try:
        meta = metadata.metadata(dist_name)
    except metadata.PackageNotFoundError:
        return None
    expr = meta.get("License-Expression")
    if expr:
        return expr
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License :: OSI Approved :: "):
            label = classifier.rsplit("::", 1)[-1].strip()
            return _CLASSIFIER_SPDX.get(label, label)
    license_field = meta.get("License")
    if license_field and "\n" not in license_field and len(license_field) < _MAX_LICENSE_LEN:
        return license_field
    return None


def _license_entries(value: str) -> list[dict[str, Any]]:
    """Build CycloneDX license entries (both declared and concluded, SPDX id when known)."""
    key = "id" if value in _SPDX_IDS else "name"
    return [
        {"license": {key: value, "acknowledgement": "declared"}},
        {"license": {key: value, "acknowledgement": "concluded"}},
    ]


def _dist_supplier(dist_name: str) -> dict[str, Any] | None:
    try:
        meta = metadata.metadata(dist_name)
    except metadata.PackageNotFoundError:
        return None
    author = meta.get("Author") or meta.get("Author-email")
    if not author:
        return None
    return {"name": re.sub(r"\s*<[^>]+>", "", author).strip() or author}


def _dist_vcs(dist_name: str) -> str | None:
    """Return a source-repository URL from the distribution metadata, if any."""
    try:
        meta = metadata.metadata(dist_name)
    except metadata.PackageNotFoundError:
        return None
    candidates: dict[str, str] = {}
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        candidates[label.strip().lower()] = url.strip()
    for key in ("source", "repository", "homepage"):
        url = candidates.get(key)
        if url and "github.com" in url:
            return url
    home = meta.get("Home-page")
    return home if home and "github.com" in home else None


def _requirement_names(dist_name: str) -> list[str]:
    try:
        dist = metadata.distribution(dist_name)
    except metadata.PackageNotFoundError:
        return []
    names: list[str] = []
    for raw in dist.requires or []:
        if "; extra" in raw:  # skip optional extras for the runtime graph
            continue
        token = re.split(r"[<>=!~;\[ (]", raw, maxsplit=1)[0].strip()
        if token:
            names.append(_normalize(token))
    return names


def enrich(sbom: dict[str, Any], lock_hashes: dict[str, list[str]]) -> dict[str, Any]:
    # Scope the SBOM to the application's runtime closure (the lockfile set).
    runtime = set(lock_hashes)
    components: list[dict[str, Any]] = [
        comp for comp in sbom.get("components", []) if _normalize(comp.get("name", "")) in runtime
    ]
    sbom["components"] = components

    ref_by_name: dict[str, str] = {}
    for comp in components:
        name = _normalize(comp.get("name", ""))
        ref_by_name[name] = comp.get("bom-ref", comp.get("purl", name))
        _enrich_component(comp, name, lock_hashes)

    _set_dependencies(sbom, components, ref_by_name)
    _set_compositions(sbom, ref_by_name)
    _set_metadata(sbom)
    return sbom


def _enrich_component(comp: dict[str, Any], name: str, lock_hashes: dict[str, list[str]]) -> None:
    digests = lock_hashes.get(name, [])
    if digests:
        comp["hashes"] = [{"alg": "SHA-256", "content": d} for d in digests]
    expr = _LICENSE_OVERRIDES.get(name) or _dist_license(comp.get("name", ""))
    if expr:
        comp["licenses"] = _license_entries(expr)
    if not comp.get("supplier"):
        supplier = _dist_supplier(comp.get("name", ""))
        if supplier:
            comp["supplier"] = supplier
    vcs = _dist_vcs(comp.get("name", ""))
    if vcs:
        refs = comp.setdefault("externalReferences", [])
        if not any(ref.get("type") == "vcs" for ref in refs):
            refs.append({"type": "vcs", "url": vcs})


def _set_compositions(sbom: dict[str, Any], ref_by_name: dict[str, str]) -> None:
    root_ref = sbom.get("metadata", {}).get("component", {}).get("bom-ref")
    assemblies = sorted(ref_by_name.values())
    if root_ref:
        assemblies = [root_ref, *assemblies]
    sbom["compositions"] = [{"aggregate": "complete", "assemblies": assemblies}]


def _set_dependencies(
    sbom: dict[str, Any], components: list[dict[str, Any]], ref_by_name: dict[str, str]
) -> None:
    deps: list[dict[str, Any]] = []
    root_ref = sbom.get("metadata", {}).get("component", {}).get("bom-ref")
    if root_ref:
        deps.append({"ref": root_ref, "dependsOn": sorted(ref_by_name.values())})
    for comp in components:
        name = comp.get("name", "")
        ref = comp.get("bom-ref", comp.get("purl"))
        if not ref:
            continue
        depends = [ref_by_name[d] for d in _requirement_names(name) if d in ref_by_name]
        deps.append({"ref": ref, "dependsOn": sorted(set(depends))})
    sbom["dependencies"] = deps


def _set_metadata(sbom: dict[str, Any]) -> None:
    meta = sbom.setdefault("metadata", {})
    meta["authors"] = [{"name": "Marc Rivero López", "email": "mriverolopez@gmail.com"}]
    meta["supplier"] = _SUPPLIER
    meta["lifecycles"] = [{"phase": "build"}]
    # BOM document data license (CC0 is the common choice for SBOM documents).
    meta["licenses"] = [{"license": {"id": "CC0-1.0"}}]
    component = meta.get("component")
    if isinstance(component, dict):
        component.setdefault("supplier", _SUPPLIER)
        version = component.get("version", "0.0.0")
        component.setdefault("purl", f"pkg:pypi/pyholded@{version}")
        component["licenses"] = _license_entries("MIT")


def _load_or_create_key(key_path: Path) -> ec.EllipticCurvePrivateKey:
    """Load a PEM P-256 private key, generating and persisting one if absent."""
    if key_path.exists():
        loaded = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if not isinstance(loaded, ec.EllipticCurvePrivateKey):
            raise TypeError(f"{key_path} is not an EC private key")
        return loaded
    private_key = ec.generate_private_key(ec.SECP256R1())
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return private_key


def _jwk(private_key: ec.EllipticCurvePrivateKey) -> dict[str, str]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url_encode(numbers.x.to_bytes(COORD_BYTES, "big")),
        "y": b64url_encode(numbers.y.to_bytes(COORD_BYTES, "big")),
    }


def sign(sbom: dict[str, Any], key_path: Path) -> None:
    """Embed a CycloneDX JSF signature (ECDSA P-256 / ES256) over the SBOM.

    Self-contained and deterministic — no external tool. The signing key is a
    standard PEM under ``key_path`` (generated on first use). The public key is
    embedded as a JWK, so the signature is independently verifiable.
    """
    private_key = _load_or_create_key(key_path)
    der_signature = private_key.sign(canonical_bytes(sbom), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    raw = r.to_bytes(COORD_BYTES, "big") + s.to_bytes(COORD_BYTES, "big")
    sbom["signature"] = {
        "algorithm": "ES256",
        "publicKey": _jwk(private_key),
        "value": b64url_encode(raw),
    }


def generate_base(venv: Path, pyproject: Path) -> dict[str, Any]:
    executable = shutil.which("cyclonedx-py")
    if executable is None:
        raise RuntimeError("cyclonedx-py not found on PATH (pip install cyclonedx-bom)")
    # Point at the venv when present; otherwise introspect the running interpreter
    # (e.g. CI installs into the system Python with no ./venv directory).
    target = [str(venv)] if venv.exists() else []
    result = subprocess.run(
        [
            executable,
            "environment",
            *target,
            "--pyproject",
            str(pyproject),
            "--output-format",
            "JSON",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    parsed: dict[str, Any] = json.loads(result.stdout)
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an enriched CycloneDX SBOM.")
    parser.add_argument("--venv", type=Path, default=Path("venv"))
    parser.add_argument("--lock", type=Path, default=Path("requirements.lock"))
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--output", type=Path, default=Path("sbom.cdx.json"))
    parser.add_argument("--sign", action="store_true", help="embed an ECDSA JSF signature")
    parser.add_argument(
        "--key", type=Path, default=Path("signing/signing-key.pem"), help="PEM signing key"
    )
    args = parser.parse_args(argv)

    # The lockfile defines the runtime scope and the component hashes; without it
    # the scope filter would silently produce an empty SBOM.
    if not args.lock.exists():
        parser.error(f"lockfile not found: {args.lock} (run `make lock` to generate it)")

    sbom = generate_base(args.venv, args.pyproject)
    lock_hashes = parse_lock_hashes(args.lock)
    enriched = enrich(sbom, lock_hashes)

    signed = False
    if args.sign:
        sign(enriched, key_path=args.key)
        signed = True

    args.output.write_text(json.dumps(enriched, indent=2) + "\n", encoding="utf-8")

    components = enriched.get("components", [])
    with_hashes = sum(1 for c in components if c.get("hashes"))
    with_licenses = sum(1 for c in components if c.get("licenses"))
    print(
        f"wrote {args.output} — {len(components)} components, "
        f"{with_hashes} with hashes, {with_licenses} with licenses, "
        f"signed={signed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
