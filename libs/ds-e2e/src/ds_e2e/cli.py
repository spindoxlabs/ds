from __future__ import annotations

import logging
import sys
from enum import Enum
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler

from ds_e2e.cleanup import provider_sync_targets, run_cleanup
from ds_e2e.config import E2ESettings
from ds_e2e.flows import CHAIN_FLOWS, FAST_FLOWS, FLOW_REGISTRY, SECURITY_FLOWS
from ds_e2e.http import HttpClient
from ds_e2e.models import FlowResult
from ds_e2e.runner import run_all, run_flow, run_selected
from ds_e2e.scenario import (
    DEFAULT_SCENARIO,
    ScenarioError,
    ScenarioRunner,
    build_runner,
)

app = typer.Typer(help="ds-e2e: End-to-end verification framework for the dataspaces platform")
console = Console()


class FlowName(str, Enum):
    api_contract = "api-contract"
    authz_perimeter = "authz-perimeter"
    user_authority = "user-authority"
    dcp_trust = "dcp-trust"
    consent_purpose = "consent-purpose"
    consent_request = "consent-request"
    org_onboarding = "org-onboarding"
    uc1 = "uc1"
    uc2 = "uc2"
    uc3 = "uc3"
    chain_community = "chain-community"
    chain_partner = "chain-partner"
    chain_unbundling = "chain-unbundling"
    semantic_model = "semantic-model"
    catalog_discovery = "catalog-discovery"
    lineage = "lineage"
    two_providers = "two-providers"
    smoke = "smoke"
    consent_withdrawal = "consent-withdrawal"
    fail_closed = "fail-closed"
    # Aggregates
    all = "all"
    fast = "fast"
    security = "security"
    chains = "chains"


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


def _print_backend(settings: E2ESettings, fmt: Format) -> None:
    """Name the data plane this run exercised, before it runs (`T-1`).

    The data plane has two implementations and a run exercises exactly one. Both
    produce the same green output, so a suite that passed against the mock and
    one that passed against the real celine `dataset-api` were indistinguishable
    afterwards — at the layer that costs the most to re-run.

    Printed *first*, not in the summary: a run that dies part-way should still
    have said what it was pointed at.
    """
    if fmt != Format.text:
        return
    console.print(f"[dim]data plane:[/dim] {settings.data_plane_label}")


def _print_summary(results: list[FlowResult], fmt: Format, settings: E2ESettings) -> None:
    """One line per flow after a multi-flow run.

    A dozen flows scroll off the screen; without a roll-up the exit code is the
    only usable signal, which is exactly the information an operator does not
    have when deciding what to look at first.
    """
    if fmt != Format.text:
        return
    console.print("\n[bold]Summary[/bold]")
    console.print(f"  [dim]data plane:[/dim] {settings.data_plane_label}")
    for r in results:
        failed = [s.name for s in r.steps if s.status == "FAIL"]
        status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        suffix = f" — first failure: {failed[0]}" if failed else ""
        console.print(f"  {status} {r.flow_name}{suffix}")


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
    _print_backend(settings, fmt)

    if clean_first:
        http = HttpClient(settings)
        try:
            run_cleanup(settings, http)
        finally:
            http.close()

    aggregates = {
        FlowName.all: None,
        FlowName.fast: FAST_FLOWS,
        FlowName.security: SECURITY_FLOWS,
        FlowName.chains: CHAIN_FLOWS,
    }
    if flow in aggregates:
        names = aggregates[flow]
        results = run_all(settings) if names is None else run_selected(names, settings)
        all_passed = all(r.passed for r in results)
        for r in results:
            _print_result(r, fmt)
        _print_summary(results, fmt, settings)
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


@app.command("sync-providers")
def sync_providers(
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Re-publish every provider's catalogue to its EDC.

    Exists because of **ordering** (`E2E-12`). `run_cleanup` syncs as its last
    step, and `e2e:prepare` then *restarts* the EDCs so they re-run their schema
    migration against the freshly recreated database — so that sync publishes
    into a store which is about to be replaced, and the catalogue it built does
    not survive.

    The REC provider usually recovered because `e2e:wait-ready` polls the
    federated catalogue for its asset and gives it time. **Nothing waited for the
    grid operator**, so its catalogue was empty or not depending on where the
    restart fell — which is how `two-providers` came to fail and then pass on a
    re-run against the same build, with no code change between.

    A verdict decided by ordering is not a verdict about the platform. This runs
    *after* the restart, so the catalogue the flows assert on is one this command
    caused rather than one it hoped for.
    """
    _setup_logging(verbose, quiet)
    settings = E2ESettings()
    http = HttpClient(settings)
    try:
        headers = http.bearer_headers()
        failures: list[str] = []
        for url, label in provider_sync_targets(settings):
            try:
                result = http.post(f"{url}/provider/sync", {}, headers=headers)
                synced = (result or {}).get("synced", []) if isinstance(result, dict) else []
                console.print(f"  synced {label}: {len(synced)} asset(s)")
                if not synced:
                    failures.append(f"{label} published nothing")
            except Exception as exc:
                failures.append(f"{label}: {exc}")
        if failures:
            # A sync that published nothing is the empty catalogue the flows
            # would then blame on the platform. Fail here, where the cause is
            # still legible.
            console.print(f"[red]provider sync incomplete:[/red] {'; '.join(failures)}")
            raise typer.Exit(code=1)
        console.print("[green]Providers re-synced[/green]")
    finally:
        http.close()


scenario_app = typer.Typer(help="Declarative fixtures for the use-case flows")
app.add_typer(scenario_app, name="scenario")


def _scenario_runner(name: str, http: HttpClient) -> ScenarioRunner:
    return build_runner(E2ESettings(), http, name)


def _run_scenario(action: str, name: str, verbose: bool, quiet: bool) -> None:
    _setup_logging(verbose, quiet)
    http = HttpClient(E2ESettings())
    try:
        runner = _scenario_runner(name, http)
        report = getattr(runner, action)()
    except ScenarioError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc
    finally:
        http.close()

    for line in report.actions:
        console.print(f"  [green]·[/green] {line}")
    for line in report.problems:
        console.print(f"  [red]![/red] {line}")
    if not report.actions and not report.problems:
        console.print("  (nothing to do)")
    raise typer.Exit(code=0 if report.ok else 1)


@scenario_app.command("apply")
def scenario_apply(
    name: Annotated[str, typer.Option("--scenario", "-s")] = DEFAULT_SCENARIO,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Provision a scenario's fixtures. Idempotent — safe to re-run."""
    _run_scenario("apply", name, verbose, quiet)


@scenario_app.command("show")
def scenario_show(
    name: Annotated[str, typer.Option("--scenario", "-s")] = DEFAULT_SCENARIO,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Report what a scenario's fixtures currently look like. Changes nothing."""
    _run_scenario("show", name, verbose, quiet)


@scenario_app.command("destroy")
def scenario_destroy(
    name: Annotated[str, typer.Option("--scenario", "-s")] = DEFAULT_SCENARIO,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Remove exactly the fixtures the scenario declares — nothing else."""
    _run_scenario("destroy", name, verbose, quiet)


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
