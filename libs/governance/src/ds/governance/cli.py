"""``ds-governance`` — validate a governance file and emit audit evidence.

Designed as a gate to run *before* a catalogue import (``POST /provider/sync``),
in CI, or against a live deployment:

    ds-governance validate --file governance.yaml
    ds-governance validate --file governance.yaml --identity-registry-url http://ir:30005
    ds-governance evidence --file governance.yaml --out-dir reports/compliance

Nothing is hardcoded to a participant, deployment, or dataset naming scheme.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from .compliance import (
    RuntimeOwnerLookup,
    build_evidence,
    fetch_participant_dids,
    fetch_participant_roles,
    load_participant_dids,
    load_participant_roles,
    render_markdown,
    validate as run_validate,
    write_artifacts,
)
from .compliance.checks import OwnerLookup, ValidationResult, load_exposed
from .mapper import GovernanceMapper
from .models import load_odrl_profile
from .owners import load_owners_yaml
from .resolver import GovernanceResolver

app = typer.Typer(
    name="ds-governance",
    help="Validate governance files and generate dataspace compliance evidence.",
    no_args_is_help=True,
)

FileOpt = typer.Option(..., "--file", "-f", help="Path to governance.yaml")
ParticipantIdOpt = typer.Option(
    "provider", help="Participant id used to derive ODRL assigner and asset ids"
)
BaseUrlOpt = typer.Option(
    "https://provider.dataspaces.localhost",
    help="Participant base URL used to derive asset and catalog IRIs",
)
ParticipantDidOpt = typer.Option(
    None,
    help="Participant DID used as the ODRL assigner when a dataset declares no "
    "resolvable owner (default: did:web:<participant-id>.dataspaces.localhost)",
)
OwnersOpt = typer.Option(
    None, help="Path to an owners YAML seed (offline owner resolution)"
)
ParticipantsOpt = typer.Option(
    None, help="Path to a participants YAML seed (offline participant DIDs)"
)
IdentityRegistryOpt = typer.Option(
    None,
    "--identity-registry-url",
    help="Resolve owners and participants against a live identity-registry "
    "instead of YAML seeds",
)
TokenOpt = typer.Option(
    None, help="Bearer token for identity-registry admin endpoints"
)
ProfileOpt = typer.Option(None, help="Path to an ODRL profile YAML")
OverlayOpt = typer.Option(
    None, help="Governance overlay name (loads governance.<name>.yaml)"
)
SharingOffersOpt = typer.Option(
    None,
    "--sharing-offers",
    help="Path to a sharing-offers YAML (default: sharing-offers.yaml next to "
    "the governance file, when present)",
)
DenyKeyOpt = typer.Option(
    None,
    "--deny-key",
    help="Glob of dataset keys that must not be exposed (repeatable), "
    "e.g. '*_dev_*' to keep test datasets out of a production catalogue",
)


def _resolve_registries(
    owners_path: Path | None,
    participants_path: Path | None,
    identity_registry_url: str | None,
    token: str | None,
) -> tuple[OwnerLookup | None, set[str] | None, dict[str, list[str]] | None, list]:
    """Build owner/participant lookups from a live registry or YAML seeds."""
    closers: list = []
    if identity_registry_url:
        lookup = RuntimeOwnerLookup(identity_registry_url, token=token)
        closers.append(lookup.close)
        return (
            lookup,
            fetch_participant_dids(identity_registry_url, token=token),
            fetch_participant_roles(identity_registry_url, token=token),
            closers,
        )

    owners = load_owners_yaml(owners_path) if owners_path else None
    return (
        owners,
        load_participant_dids(participants_path),
        load_participant_roles(participants_path),
        closers,
    )


def _resolve_sharing_offers(governance_file: Path, explicit: Path | None) -> Path | None:
    """An explicit path wins; otherwise pick up the sibling file by convention."""
    if explicit is not None:
        return explicit
    sibling = governance_file.parent / "sharing-offers.yaml"
    return sibling if sibling.exists() else None


def _emit(result: ValidationResult, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(result.asdict(), indent=2, sort_keys=True))
        return
    if output_format == "markdown":
        typer.echo(render_markdown(result))
        return

    typer.echo(f"Governance validation: {'PASS' if result.passed else 'FAIL'}")
    typer.echo(f"Governance: {result.governance_path}")
    typer.echo(f"Datasets checked: {result.datasets_checked}")
    if result.offers_checked:
        typer.echo(f"Sharing offers checked: {result.offers_checked}")
    if result.artifacts:
        typer.echo("Artifacts:")
        for name, path in result.artifacts.items():
            typer.echo(f"- {name}: {path}")
    for label, findings in (("Errors", result.errors), ("Warnings", result.warnings)):
        if not findings:
            continue
        typer.echo(f"\n{label}:")
        for finding in findings:
            dataset = f" {finding.dataset}:" if finding.dataset else ""
            typer.echo(f"- [{finding.check}]{dataset} {finding.message}")


@app.command()
def validate(
    file: Path = FileOpt,
    participant_id: str = ParticipantIdOpt,
    base_url: str = BaseUrlOpt,
    participant_did: str = ParticipantDidOpt,
    owners: Path = OwnersOpt,
    participants: Path = ParticipantsOpt,
    identity_registry_url: str = IdentityRegistryOpt,
    token: str = TokenOpt,
    profile: Path = ProfileOpt,
    overlay: str = OverlayOpt,
    sharing_offers: Path = SharingOffersOpt,
    deny_key: list[str] = DenyKeyOpt,
    output_format: str = typer.Option(
        "text", "--format", help="text | json | markdown"
    ),
    strict: bool = typer.Option(
        False, help="Treat warnings as failures"
    ),
):
    """Validate a governance file before importing it into a connector."""
    owner_lookup, participant_dids, participant_roles, closers = _resolve_registries(
        owners, participants, identity_registry_url, token
    )
    try:
        result = run_validate(
            file,
            participant_id=participant_id,
            base_url=base_url,
            participant_did=participant_did,
            owners=owner_lookup,
            participant_dids=participant_dids,
            profile=load_odrl_profile(profile) if profile else None,
            overlay_name=overlay,
            deny_key_patterns=list(deny_key or []),
            sharing_offers_path=_resolve_sharing_offers(file, sharing_offers),
            participant_roles=participant_roles,
        )
    finally:
        for close in closers:
            close()

    _emit(result, output_format)
    failed = not result.passed or (strict and result.warnings)
    raise typer.Exit(1 if failed else 0)


@app.command()
def evidence(
    file: Path = FileOpt,
    out_dir: Path = typer.Option(
        Path("reports/compliance"), "--out-dir", help="Directory for evidence artifacts"
    ),
    name: str = typer.Option("governance", help="Artifact filename prefix"),
    participant_id: str = ParticipantIdOpt,
    base_url: str = BaseUrlOpt,
    publisher_id: str = typer.Option(
        None, help="Publisher IRI for the DCAT catalog (default: did:web of base URL host)"
    ),
    publisher_name: str = typer.Option("Dataspace Provider", help="Publisher display name"),
    participant_did: str = ParticipantDidOpt,
    owners: Path = OwnersOpt,
    participants: Path = ParticipantsOpt,
    identity_registry_url: str = IdentityRegistryOpt,
    token: str = TokenOpt,
    profile: Path = ProfileOpt,
    overlay: str = OverlayOpt,
    sharing_offers: Path = SharingOffersOpt,
    deny_key: list[str] = DenyKeyOpt,
):
    """Validate, then write DCAT-AP catalog and ODRL offers as audit evidence."""
    odrl_profile = load_odrl_profile(profile) if profile else None
    owner_lookup, participant_dids, participant_roles, closers = _resolve_registries(
        owners, participants, identity_registry_url, token
    )
    try:
        result = run_validate(
            file,
            participant_id=participant_id,
            base_url=base_url,
            participant_did=participant_did,
            owners=owner_lookup,
            participant_dids=participant_dids,
            profile=odrl_profile,
            overlay_name=overlay,
            deny_key_patterns=list(deny_key or []),
            sharing_offers_path=_resolve_sharing_offers(file, sharing_offers),
            participant_roles=participant_roles,
        )
    finally:
        for close in closers:
            close()

    if result.datasets_checked == 0:
        _emit(result, "text")
        typer.echo("\nNo exposed dataset — no evidence generated.", err=True)
        raise typer.Exit(1)

    resolver = GovernanceResolver.from_file_with_override(file, overlay_name=overlay)
    mapper = GovernanceMapper(
        participant_id=participant_id,
        base_url=base_url,
        profile=odrl_profile,
        participant_did=participant_did,
    )
    exposed = load_exposed(resolver, mapper)
    catalog, offers = build_evidence(
        exposed,
        mapper,
        base_url=base_url,
        publisher_id=publisher_id or f"did:web:{base_url.split('://')[-1].rstrip('/')}",
        publisher_name=publisher_name,
        catalog_name=name,
    )
    write_artifacts(
        result, catalog, offers, out_dir, profile=mapper.profile, name=name
    )

    _emit(result, "text")
    raise typer.Exit(0 if result.passed else 1)


def main() -> None:
    sys.exit(app())


if __name__ == "__main__":
    main()
