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
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from importlib import metadata
from pathlib import Path
from typing import Any

_EC_POINT_LEN = 65  # uncompressed P-256 point: 0x04 || X(32) || Y(32)
_EC_UNCOMPRESSED = 0x04

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


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _public_key_jwk(pub_pem: Path) -> dict[str, str]:
    """Derive a P-256 JWK from a PEM EC public key (SubjectPublicKeyInfo)."""
    body = "".join(
        line for line in pub_pem.read_text(encoding="utf-8").splitlines() if "-----" not in line
    )
    der = base64.b64decode(body)
    point = der[-_EC_POINT_LEN:]
    if point[0] != _EC_UNCOMPRESSED:
        raise ValueError("unexpected EC public key encoding (not uncompressed P-256)")
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(point[1:33]),
        "y": _b64url(point[33:65]),
    }


def _canonical_bytes(sbom: dict[str, Any]) -> bytes:
    """Deterministic JSON bytes of the SBOM (signature excluded) — the signing payload."""
    payload = {key: value for key, value in sbom.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign(
    sbom: dict[str, Any], key: Path, pub: Path, signing_config: Path, bundle_out: Path
) -> None:
    """Embed a JSF signature produced by cosign (offline, no transparency log)."""
    cosign = shutil.which("cosign")
    if cosign is None:
        raise RuntimeError("cosign not found on PATH")
    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as payload_file:
        payload_file.write(_canonical_bytes(sbom))
        payload_path = Path(payload_file.name)
    # A signing-config (newer cosign) keeps signing offline (no transparency log).
    # Older cosign signs offline by default and has no such config — only pass it
    # when present so both generations work.
    config_args = ["--signing-config", str(signing_config)] if signing_config.exists() else []
    try:
        subprocess.run(
            [
                cosign,
                "sign-blob",
                "--key",
                str(key),
                "--yes",
                *config_args,
                "--bundle",
                str(bundle_out),
                str(payload_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "COSIGN_PASSWORD": os.environ.get("COSIGN_PASSWORD", "")},
        )
    finally:
        payload_path.unlink(missing_ok=True)
    bundle = json.loads(bundle_out.read_text(encoding="utf-8"))
    signature = bundle["messageSignature"]["signature"]
    sbom["signature"] = {
        "algorithm": "ES256",
        "publicKey": _public_key_jwk(pub),
        "value": signature,
    }


def generate_base(venv: Path, pyproject: Path) -> dict[str, Any]:
    executable = shutil.which("cyclonedx-py")
    if executable is None:
        raise RuntimeError("cyclonedx-py not found on PATH (pip install cyclonedx-bom)")
    result = subprocess.run(
        [
            executable,
            "environment",
            str(venv),
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
    parser.add_argument("--sign", action="store_true", help="embed a cosign JSF signature")
    parser.add_argument("--signing-dir", type=Path, default=Path("signing"))
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
        sign(
            enriched,
            key=args.signing_dir / "cosign.key",
            pub=args.signing_dir / "cosign.pub",
            signing_config=args.signing_dir / "signing-config.json",
            bundle_out=args.output.with_suffix(args.output.suffix + ".bundle"),
        )
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
