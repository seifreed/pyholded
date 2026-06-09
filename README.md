<p align="center">
  <img src="https://img.shields.io/badge/pyholded-Holded%20API%20v2%20client-blue?style=for-the-badge" alt="pyholded">
</p>

<h1 align="center">pyholded</h1>

<p align="center">
  <strong>Modular Python client and CLI for the complete Holded API v2</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/pyholded/"><img src="https://img.shields.io/pypi/v/pyholded?style=flat-square&logo=pypi&logoColor=white" alt="PyPI Version"></a>
  <a href="https://pypi.org/project/pyholded/"><img src="https://img.shields.io/pypi/pyversions/pyholded?style=flat-square&logo=python&logoColor=white" alt="Python Versions"></a>
  <a href="https://github.com/seifreed/pyholded/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
  <a href="https://github.com/seifreed/pyholded/actions"><img src="https://img.shields.io/github/actions/workflow/status/seifreed/pyholded/ci.yml?style=flat-square&logo=github&label=CI" alt="CI Status"></a>
  <a href="https://github.com/seifreed/pyholded"><img src="https://img.shields.io/badge/types-py.typed-brightgreen?style=flat-square" alt="Typed"></a>
  <a href="https://github.com/seifreed/pyholded/blob/main/sbom.cdx.json"><img src="https://img.shields.io/badge/SBOM-CycloneDX%209.3%2FA%20signed-brightgreen?style=flat-square" alt="SBOM"></a>
</p>

<p align="center">
  <a href="https://github.com/seifreed/pyholded/stargazers"><img src="https://img.shields.io/github/stars/seifreed/pyholded?style=flat-square" alt="GitHub Stars"></a>
  <a href="https://github.com/seifreed/pyholded/issues"><img src="https://img.shields.io/github/issues/seifreed/pyholded?style=flat-square" alt="GitHub Issues"></a>
  <a href="https://buymeacoffee.com/seifreed"><img src="https://img.shields.io/badge/Buy%20Me%20a%20Coffee-support-yellow?style=flat-square&logo=buy-me-a-coffee&logoColor=white" alt="Buy Me a Coffee"></a>
</p>

---

## Overview

**pyholded** is a Python toolkit to talk to the [Holded](https://developers.holded.com)
business-management API (v2). Every endpoint across all modules — sales/purchase
documents, contacts, products, CRM, projects and team — is described in a single
declarative registry from which both the typed client and the CLI are generated.
Results print as rich tables, JSON, or TOON.

### Key Features

| Feature | Description |
|---------|-------------|
| **Registry-driven** | Every endpoint is data; client and CLI share one source of truth |
| **Full v2 surface** | Documents, contacts, products, CRM, projects, team — plus a `raw` escape hatch |
| **Bearer auth** | Token from `--token`, environment variable, or TOML config file |
| **Cursor pagination** | `--all` (CLI) / `paginate=True` (library) merges every page |
| **Three outputs** | Rich tables, JSON, and TOON (token-efficient for LLMs) |
| **CLI + Library** | Use as a command-line tool or a typed Python package (`py.typed`) |
| **Strict quality gate** | ruff, black, mypy (strict), bandit, vulture, pip-audit — zero suppressions |

### Supported Outputs

```text
Records       rich tables, JSON, TOON
Pagination    cursor-based ({items, cursor, has_more}); --all merges pages
Auth          Authorization: Bearer <PAT> via env var or config file
Binary        PDF download for any document type (invoices, credit-notes, ...)
```

---

## Installation

### From PyPI (Recommended)

```bash
pip install pyholded
```

### From Source

```bash
git clone https://github.com/seifreed/pyholded.git
cd pyholded
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

### Optional Extras

```bash
pip install "pyholded[dev]"   # ruff, black, mypy, bandit, vulture, pip-audit, pytest
```

---

## Authentication

Holded API v2 uses a Personal Access Token (`pat_…`) sent as `Authorization: Bearer`.
Generate one in Holded: **Settings → Developers → Credentials → Add API Token**.

The token is resolved in order of precedence:

1. An explicit value (`--token`, or `HoldedClient(token=...)`).
2. The `HOLDED_TOKEN` environment variable (`HOLDED_API_KEY` also accepted).
3. A TOML config file (`--config`, `HOLDED_CONFIG`, or `~/.config/pyholded/config.toml`).

```toml
# ~/.config/pyholded/config.toml
[holded]
token = "pat_xxx_yyy"
# base_url = "https://api.holded.com/api/v2/"   # optional override
```

### Multiple accounts

Configure several Holded accounts and query one or all of them.

Environment variables — `HOLDED_TOKEN` is the `default` account; `HOLDED_TOKEN_<NAME>`
adds a named account:

```bash
export HOLDED_TOKEN="pat_default"
export HOLDED_TOKEN_ACME="pat_acme"
export HOLDED_TOKEN_PERSONAL="pat_personal"
```

Config file — per-account tables (env overrides the file for the same name):

```toml
# ~/.config/pyholded/config.toml
default_account = "acme"          # optional; picks the account when none is given

[accounts.acme]
token = "pat_acme"
# base_url = "..."                # optional, per account

[accounts.personal]
token = "pat_personal"
```

Select with `--account <name>` (CLI) / `HoldedClient(account="acme")` (library), or fan
out to every account with `--all-accounts` / `MultiClient`. When several accounts are
configured and none is selected, set `default_account` or pass one explicitly.

---

## Quick Start

```bash
# List every resource and its operations
holded resources

# List records (pretty table by default)
holded contacts list --limit 5

# TOON output, ideal for LLM contexts
holded taxes list -o toon
```

---

## Usage

### Command Line Interface

```bash
# List a page, or follow the cursor and fetch all pages
holded invoices list --limit 50
holded expenses_accounts list --all -o json

# Get one record, in JSON
holded contacts get --id 0123456789abcdef01234567 -o json

# Download a document PDF (binary)
holded invoices get-pdf --id 89abcdef0123456789abcdef > invoice.pdf

# Create from inline JSON, a file, or key=value fields
holded contacts create --data '{"name": "ACME SL"}'
holded contacts create --data @contact.json
holded contacts create --field name=ACME --field code=B12345678

# Multiple accounts
holded accounts                               # list configured accounts
holded --account acme contacts list           # one named account
holded --all-accounts contacts list -o json   # fan out -> {account: result}

# Call any endpoint directly
holded raw GET taxes -o toon
```

### Main Commands

| Command | Description |
|--------|-------------|
| `holded resources` | List all resources and their operations |
| `holded accounts` | List configured accounts (names + base URLs; tokens never shown) |
| `holded <resource> list` | List records (cursor-paginated; `--all` fetches every page) |
| `holded <resource> get --id <id>` | Get a single record |
| `holded <resource> create --data <json>` | Create a record |
| `holded <resource> update --id <id> --data <json>` | Update a record |
| `holded <resource> delete --id <id>` | Delete a record |
| `holded invoices get-pdf --id <id>` | Download a document PDF (also `send`) |
| `holded raw <METHOD> <PATH>` | Call an arbitrary endpoint |

### Options

| Option | Description |
|--------|-------------|
| `-o, --output {rich,json,toon}` | Output format (global default or per-command override) |
| `-a, --account <name>` | Use a named account (env/config) |
| `--all-accounts` | Run the command on every configured account |
| `--all` | Follow the cursor and fetch every page (GET) |
| `--limit`, `--cursor` | Manual pagination controls |
| `--data <json\|@file>`, `--field k=v` | Request body for create/update |
| `--token`, `--config`, `--base-url`, `--timeout` | Connection options |

### Resources

| Group | Resources |
|-------|-----------|
| **Documents** (CRUD + `get-pdf`, `send`) | `invoices`, `credit_notes`, `sales_orders`, `estimates`, `proformas`, `waybills`, `sales_receipts`, `purchases`, `purchase_orders` |
| **Masters** (CRUD) | `contacts`, `contact_groups`, `products`, `services`, `warehouses`, `payments`, `sales_channels`, `expenses_accounts`, `taxes`, `payment_methods` |
| **CRM** | `funnels`, `leads` (+ `create-note`, `create-task`), `events`, `bookings`, `booking_locations` |
| **Projects / Team** | `projects`, `tasks`, `employees` |

---

## Python Library

### Basic Usage

```python
from pyholded import HoldedClient

with HoldedClient() as client:                       # token from env or config file
    page = client.invoices.list(params={"limit": 50})
    everyone = client.contacts.list(paginate=True)   # all pages, merged items list
    contact = client.contacts.get(id="0123456789abcdef01234567")
    pdf = client.invoices.getPdf(id="89abcdef0123456789abcdef")   # raw bytes

    new = client.contacts.create(data={"name": "ACME SL", "code": "B12345678"})

    # Any endpoint, even one not modelled, is reachable directly:
    raw = client.request("GET", "taxes", params={"limit": 5})
```

Resources are attributes; operations are methods. Path parameters (`id`) are keyword
arguments, query parameters go in `params=`, and the request body in `data=`.

### Multiple accounts

```python
from pyholded import HoldedClient, MultiClient

# one named account
with HoldedClient(account="acme") as client:
    invoices = client.invoices.list()

# every configured account at once -> {account: result}
with MultiClient.from_accounts() as multi:           # or from_accounts(["acme", "personal"])
    per_account = multi.contacts.list(params={"limit": 5})
    # {"acme": {"items": [...]}, "personal": {"items": [...]}}
```

A failure on one account is captured as `{"error": "..."}` for that account, so the
others still return their data.

### Output Helpers

```python
from pyholded import OutputFormat, render, to_json, to_toon

render(page, OutputFormat.TOON)   # print in TOON
print(to_json(page))              # canonical JSON string
print(to_toon(page))              # TOON string
```

---

## Supply Chain / SBOM

A CycloneDX 1.6 SBOM ([`sbom.cdx.json`](sbom.cdx.json)) is generated from real data —
package SHA-256 hashes come from a `uv`-compiled hashed lockfile
([`requirements.lock`](requirements.lock)), licenses and suppliers from installed
package metadata, a full dependency graph, and an **ECDSA P-256 (ES256) signature**
embedded as a CycloneDX JSF block (pure-Python, offline, no external tools). CI
regenerates, scores and verifies it on every push.

```bash
make sbom          # generate + sign sbom.cdx.json
make sbom-score    # generate + score with sbomqs (fails below 9.0)
make sbom-verify   # verify the embedded signature
make lock          # refresh the hashed lockfile (uv)
```

Current [sbomqs](https://github.com/interlynk-io/sbomqs) score: **9.3 / 10 (Grade A)** —
Identification, Provenance, Integrity, Licensing, Vulnerability and Structural all at A.
Completeness (D) is capped by sbomqs's CycloneDX dependency-graph detection, not by
missing data (the `dependencies` and `compositions` are present and valid). A perfect
10/A is not attainable for a PyPI project (it also requires per-component CPEs, which
Python packages do not have).

The signing private key is never committed; the public key travels inside the SBOM
(`signature.publicKey` JWK), so `scripts/verify_sbom.py` verifies it with no extra files.

## Requirements

- Python 3.14+
- See [pyproject.toml](pyproject.toml) for dependencies and extras

---

## Contributing

Contributions are welcome.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

All changes must keep the full quality gate green (`ruff`, `black`, `mypy --strict`,
`bandit`, `vulture`, `pip-audit`, `pytest`) with zero in-line suppressions.

---

## Support the Project

If this project is useful in your workflows, you can support development:

<a href="https://buymeacoffee.com/seifreed" target="_blank">
  <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="50">
</a>

---

## License

This project is licensed under the MIT license. See [LICENSE](LICENSE).

**Attribution**
- Author: **Marc Rivero López** | [@seifreed](https://github.com/seifreed)
- Repository: [github.com/seifreed/pyholded](https://github.com/seifreed/pyholded)

---

<p align="center">
  <sub>Built for practical Holded automation and business-data workflows</sub>
</p>
