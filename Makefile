.PHONY: install gate lint format types security deadcode audit test \
        sbom sbom-score sbom-verify lock all

VENV ?= venv
PY := $(VENV)/bin/python
SBOM := sbom.cdx.json
SBOM_MIN_SCORE ?= 9.0

install:
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check .

format:
	$(PY) -m black --check --diff .

types:
	$(PY) -m mypy

security:
	$(PY) -m bandit -rq src -c pyproject.toml

deadcode:
	$(PY) -m vulture src/

audit:
	$(PY) -m pip_audit -r requirements.lock --strict

test:
	$(PY) -m pytest

gate: lint format types security deadcode test

lock:
	uv pip compile pyproject.toml --generate-hashes -o requirements.lock

sbom:
	$(PY) scripts/generate_sbom.py --sign --output $(SBOM)

sbom-verify:
	$(PY) scripts/verify_sbom.py $(SBOM)

sbom-score: sbom
	sbomqs score $(SBOM)
	@score=$$(sbomqs score $(SBOM) --basic | cut -f1); \
	awk -v s=$$score -v m=$(SBOM_MIN_SCORE) 'BEGIN { if (s+0 < m+0) { printf "SBOM score %.1f below minimum %.1f\n", s, m; exit 1 } printf "SBOM score %.1f >= %.1f OK\n", s, m }'

all: gate sbom-score sbom-verify
