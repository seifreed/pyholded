"""Command-line interface for the Holded API.

The CLI mirrors the endpoint registry: every resource is a command group and
every operation a subcommand whose path/query parameters are flags. Output is
selectable per invocation (``--output rich|json|toon``)::

    holded invoices list --limit 50
    holded contacts get --id 0123456789abcdef01234567 --output json
    holded --account acme contacts list          # one named account
    holded --all-accounts contacts list          # fan out to every account
    holded accounts                               # list configured accounts
    holded raw GET taxes --output toon
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from ._registry import Endpoint, Resource
from .client import HoldedClient
from .config import resolve_accounts
from .endpoints import REGISTRY
from .exceptions import HoldedError
from .multi import MultiClient
from .output import OutputFormat, render


class _Context:
    """Shared CLI state carried on the click context object."""

    def __init__(
        self,
        token: str | None,
        config: Path | None,
        base_url: str | None,
        output: str,
        timeout: float,
        account: str | None,
        all_accounts: bool,
    ) -> None:
        self.token = token
        self.config = config
        self.base_url = base_url
        self.output = OutputFormat(output)
        self.timeout = timeout
        self.account = account
        self.all_accounts = all_accounts

    def client(self) -> HoldedClient:
        return HoldedClient(
            self.token,
            account=self.account,
            base_url=self.base_url,
            config_path=self.config,
            timeout=self.timeout,
        )

    def multi(self) -> MultiClient:
        return MultiClient.from_accounts(config_path=self.config, timeout=self.timeout)

    def run_call(self, resource: str, operation: str, **kwargs: Any) -> Any:
        """Run an operation on the selected account, or fan out to all accounts."""
        if self.all_accounts:
            with self.multi() as multi:
                return multi.call(resource, operation, **kwargs)
        with self.client() as client:
            return client.call(resource, operation, **kwargs)

    def run_request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self.all_accounts:
            with self.multi() as multi:
                return multi.request(method, path, **kwargs)
        with self.client() as client:
            return client.request(method, path, **kwargs)

    def resolve_format(self, override: str | None) -> OutputFormat:
        """Per-command --output wins over the group-level default."""
        return OutputFormat(override) if override else self.output


_OUTPUT_CHOICES = [fmt.value for fmt in OutputFormat]


def _output_option() -> click.Option:
    return click.Option(
        ["-o", "--output"],
        type=click.Choice(_OUTPUT_CHOICES),
        default=None,
        help="Output format (overrides the global default).",
    )


def _to_flag(name: str) -> str:
    out = [name[0].lower()]
    for char in name[1:]:
        if char.isupper():
            out.append("-")
            out.append(char.lower())
        else:
            out.append(char)
    return "--" + "".join(out).replace("_", "-")


def _dest(name: str) -> str:
    return _to_flag(name)[2:].replace("-", "_")


def _kebab(name: str) -> str:
    return _to_flag(name)[2:]


def _parse_data(data: str | None, fields: tuple[str, ...]) -> Any:
    body: Any = None
    if data is not None:
        if data.startswith("@"):
            path = Path(data[1:])
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise click.BadParameter(f"cannot read {path}: {exc}", param_hint="--data") from exc
        else:
            text = data
        try:
            body = json.loads(text)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(f"invalid JSON: {exc}", param_hint="--data") from exc
    if fields:
        merged: dict[str, str] = body if isinstance(body, dict) else {}
        for item in fields:
            key, _, value = item.partition("=")
            merged[key] = value
        body = merged
    return body


def _operation_command(resource: Resource, endpoint: Endpoint) -> click.Command:
    params: list[click.Parameter] = []
    path_dests = {name: _dest(name) for name in endpoint.path_params}
    query_dests = {name: _dest(name) for name in endpoint.query_params}

    for name in endpoint.path_params:
        params.append(click.Option([_to_flag(name)], required=True, help="path parameter"))
    for name in endpoint.query_params:
        params.append(click.Option([_to_flag(name)], required=False, help="query parameter"))
    if endpoint.has_body:
        params.append(
            click.Option(
                ["--data"],
                required=False,
                help="JSON request body, or @file.json to read from a file",
            )
        )
        params.append(
            click.Option(
                ["--field", "fields"],
                multiple=True,
                help="body field as key=value (repeatable)",
            )
        )
    paginates = endpoint.method == "GET" and not endpoint.binary
    if paginates:
        params.append(
            click.Option(
                ["--all", "fetch_all"],
                is_flag=True,
                help="follow the cursor and fetch every page",
            )
        )
    params.append(_output_option())

    def callback(**kwargs: Any) -> None:
        ctx = click.get_current_context()
        state: _Context = ctx.obj
        path_params = {
            name: kwargs[dest] for name, dest in path_dests.items() if kwargs.get(dest) is not None
        }
        query = {
            name: kwargs[dest] for name, dest in query_dests.items() if kwargs.get(dest) is not None
        }
        data = (
            _parse_data(kwargs.get("data"), kwargs.get("fields", ())) if endpoint.has_body else None
        )
        result = state.run_call(
            resource.name,
            endpoint.name,
            path_params=path_params,
            params=query or None,
            data=data,
            paginate=bool(kwargs.get("fetch_all")),
        )
        render(result, state.resolve_format(kwargs.get("output")))

    return click.Command(
        name=_kebab(endpoint.name),
        params=params,
        callback=callback,
        help=endpoint.description or f"{endpoint.method} {endpoint.path}",
        short_help=endpoint.description,
    )


def _resource_group(resource: Resource) -> click.Group:
    group = click.Group(
        name=resource.name,
        help=f"[{resource.module}] {resource.description}",
    )
    for endpoint in resource.endpoints:
        group.add_command(_operation_command(resource, endpoint))
    return group


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--token", envvar="HOLDED_TOKEN", help="Holded API token (PAT).")
@click.option("-a", "--account", help="Use a named account from env/config.")
@click.option("--all-accounts", is_flag=True, help="Run on every configured account.")
@click.option(
    "--config",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    help="Path to a TOML config file.",
)
@click.option("--base-url", help="Override the API base URL.")
@click.option(
    "-o",
    "--output",
    type=click.Choice(_OUTPUT_CHOICES),
    default=OutputFormat.RICH.value,
    show_default=True,
    help="Default output format.",
)
@click.option("--timeout", type=float, default=30.0, show_default=True, help="HTTP timeout (s).")
@click.pass_context
def cli(
    ctx: click.Context,
    token: str | None,
    account: str | None,
    all_accounts: bool,
    config: Path | None,
    base_url: str | None,
    output: str,
    timeout: float,
) -> None:
    """Modular command-line client for the complete Holded API."""
    ctx.obj = _Context(token, config, base_url, output, timeout, account, all_accounts)


@cli.command(name="resources")
@click.option("-o", "--output", type=click.Choice(_OUTPUT_CHOICES), default=None)
@click.pass_context
def list_resources(ctx: click.Context, output: str | None) -> None:
    """List every resource and its operations."""
    state: _Context = ctx.obj
    overview = {
        resource.name: {
            "module": resource.module,
            "operations": [ep.name for ep in resource.endpoints],
        }
        for resource in REGISTRY
    }
    render(overview, state.resolve_format(output))


@cli.command(name="raw")
@click.argument("method")
@click.argument("path")
@click.option("--param", "params", multiple=True, help="query parameter key=value (repeatable)")
@click.option("--data", help="JSON request body, or @file.json")
@click.option("--binary", is_flag=True, help="treat the response as raw bytes")
@click.option("-o", "--output", type=click.Choice(_OUTPUT_CHOICES), default=None)
@click.pass_context
def raw(
    ctx: click.Context,
    method: str,
    path: str,
    params: tuple[str, ...],
    data: str | None,
    binary: bool,
    output: str | None,
) -> None:
    """Call an arbitrary endpoint: METHOD and PATH (relative to the API base URL)."""
    state: _Context = ctx.obj
    query = dict(item.partition("=")[::2] for item in params) or None
    body = _parse_data(data, ()) if data else None
    result = state.run_request(method, path.lstrip("/"), params=query, json=body, binary=binary)
    if binary and isinstance(result, bytes):
        sys.stdout.buffer.write(result)
        return
    render(result, state.resolve_format(output))


@cli.command(name="accounts")
@click.option("-o", "--output", type=click.Choice(_OUTPUT_CHOICES), default=None)
@click.pass_context
def list_accounts(ctx: click.Context, output: str | None) -> None:
    """List configured accounts (names and base URLs; tokens are never shown)."""
    state: _Context = ctx.obj
    accounts = resolve_accounts(state.config)
    overview = [
        {"account": name, "base_url": cfg.base_url} for name, cfg in sorted(accounts.items())
    ]
    render(overview, state.resolve_format(output))


def _register_resources() -> None:
    for resource in REGISTRY:
        cli.add_command(_resource_group(resource))


def main() -> None:
    """Console-script entry point."""
    _register_resources()
    try:
        cli.main(standalone_mode=False)
    except HoldedError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)
    except click.ClickException as exc:
        exc.show()
        sys.exit(exc.exit_code)
    except click.exceptions.Abort:
        sys.exit(130)


if __name__ == "__main__":
    main()
