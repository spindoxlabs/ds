from __future__ import annotations

import logging
import sys
from enum import Enum
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler

from ds_e2e.cleanup import run_cleanup
from ds_e2e.config import E2ESettings
from ds_e2e.flows import FLOW_REGISTRY
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult
from ds_e2e.runner import run_all, run_flow

app = typer.Typer(help="ds-e2e: End-to-end verification framework for the dataspaces platform")
console = Console()


class FlowName(str, Enum):
    smoke = "smoke"
    uc1 = "uc1"
    uc2 = "uc2"
    uc3 = "uc3"
    all = "all"


class Format(str, Enum):
    text = "text"
    json = "json"
    markdown = "markdown"


def _setup_logging(verbose: bool, quiet: bool) -> None:
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=False, markup=True)],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _print_result(result: FlowResult, fmt: Format) -> None:
    if fmt == Format.json:
        console.print_json(result.to_json())
    elif fmt == Format.markdown:
        console.print(result.to_markdown())
    else:
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        console.print(f"\n{result.flow_name}: {status}")
        for step in result.steps:
            icon = "[green]PASS[/green]" if step.status == "PASS" else "[red]FAIL[/red]"
            detail = f" — {step.detail}" if step.detail else ""
            console.print(f"  {icon} {step.name}{detail}")


@app.command()
def run(
    flow: Annotated[FlowName, typer.Option("--flow", "-f", help="Flow to execute")] = FlowName.smoke,
    clean_first: Annotated[bool, typer.Option("--clean-first", help="Run cleanup before executing")] = False,
    fmt: Annotated[Format, typer.Option("--format", help="Output format")] = Format.text,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Execute one or all E2E verification flows."""
    _setup_logging(verbose, quiet)
    settings = E2ESettings()

    if clean_first:
        http = HttpClient(settings)
        try:
            run_cleanup(settings, http)
        finally:
            http.close()

    if flow == FlowName.all:
        results = run_all(settings)
        all_passed = all(r.passed for r in results)
        for r in results:
            _print_result(r, fmt)
        raise typer.Exit(code=0 if all_passed else 1)
    else:
        result = run_flow(flow.value, settings)
        _print_result(result, fmt)
        raise typer.Exit(code=0 if result.passed else 1)


@app.command()
def clean(
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Reset runtime state: truncate connector/provenance tables and re-sync provider."""
    _setup_logging(verbose, quiet)
    settings = E2ESettings()
    http = HttpClient(settings)
    try:
        run_cleanup(settings, http)
        console.print("[green]Cleanup complete[/green]")
    finally:
        http.close()


@app.command()
def health(
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Check reachability of all platform services."""
    _setup_logging(verbose, quiet)
    settings = E2ESettings()
    http = HttpClient(settings)
    services = {
        "provider connector": settings.connector_url,
        "consumer connector": settings.consumer_connector_url,
        "dataset-api": settings.dataset_api_url,
        "provider provenance": settings.provenance_url,
        "consumer provenance": settings.consumer_provenance_url,
        "identity-registry": settings.identity_registry_url,
    }
    all_ok = True
    try:
        for name, url in services.items():
            try:
                http.get(f"{url}/health")
                console.print(f"  [green]OK[/green] {name} ({url})")
            except Exception as exc:
                console.print(f"  [red]FAIL[/red] {name} ({url}) — {exc}")
                all_ok = False
    finally:
        http.close()

    raise typer.Exit(code=0 if all_ok else 1)


if __name__ == "__main__":
    app()
