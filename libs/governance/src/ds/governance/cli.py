"""``ds-governance`` — validate a governance file and emit audit evidence.

Designed as a gate to run *before* a catalogue import (``POST /provider/sync``),
in CI, or against a live deployment:

    ds-governance validate --file governance.yaml
    ds-governance validate --file governance.yaml --identity-registry-url http://ir:30005
    ds-governance evidence --file governance.yaml --out-dir reports/compliance

Nothing is hardcoded to a participant, deployment, or dataset naming scheme.
"""

from __future__ import annotations
from typing import Any

import json
import sys
from pathlib import Path

import typer

from .compliance import (
    RuntimeOwnerLookup,
    build_evidence,
    fetch_participant_dids,
    load_participant_dids,
    render_markdown,
    validate as run_validate,
    write_artifacts,
)
from .compliance.checks import OwnerLookup, ValidationResult, load_exposed
from .mapper import GovernanceMapper
from .models import load_odrl_profile
from .owners import load_owners_yaml
from .resolver import GovernanceResolver
from .vocabularies import load_vocabularies

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
    "https://rec.dataspaces.localhost",
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
TokenOpt = typer.Option(None, help="Bearer token for identity-registry admin endpoints")
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
) -> tuple[OwnerLookup | None, set[str] | None, list[Any]]:
    """Build owner/participant lookups from a live registry or YAML seeds."""
    closers: list[Any] = []
    if identity_registry_url:
        lookup = RuntimeOwnerLookup(identity_registry_url, token=token)
        closers.append(lookup.close)
        dids = fetch_participant_dids(identity_registry_url, token=token)
        # **Asking for a live check and not getting one is a failure, not a
        # quieter pass.** The fetch answers `None` when the registry cannot be
        # read, and `owner-participant` reads `None` as "nothing to compare" and
        # returns — which is the correct behaviour for an *offline* run and
        # exactly wrong here, where the caller named a registry on the command
        # line.
        #
        # This is not hypothetical. `runtime.py` requested `/participants`, a
        # route that does not exist, so the fetch 404'd and the check skipped —
        # against every registry, since the flag was added. The rulebook
        # meanwhile recorded it as running here. Fixing the path without closing
        # the silence would leave the same trap set for the next wrong URL or
        # missing token.
        if dids is None:
            raise RuntimeError(
                f"Cannot read participants from {identity_registry_url}. "
                "`--identity-registry-url` was given, so `owner-participant` was "
                "meant to run and cannot — check the URL and that `--token` "
                "carries `identity-registry.admin` or a read scope. Refusing "
                "rather than reporting a pass that check did not make."
            )
        return (lookup, dids, closers)

    owners = load_owners_yaml(owners_path) if owners_path else None
    return (owners, load_participant_dids(participants_path), closers)


def _resolve_sharing_offers(
    governance_file: Path, explicit: Path | None
) -> Path | None:
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
    vocabularies: Path = typer.Option(
        None,
        "--vocabularies",
        help="Path to vocabularies.yaml. Given, a dataset naming a semantic model "
        "nobody registered is reported; omitted, registration is not checked at all.",
    ),
    deny_key: list[str] = DenyKeyOpt,
    output_format: str = typer.Option(
        "text", "--format", help="text | json | markdown"
    ),
    strict: bool = typer.Option(False, help="Treat warnings as failures"),
) -> None:
    """Validate a governance file before importing it into a connector."""
    owner_lookup, participant_dids, closers = _resolve_registries(
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
            vocabularies=(
                load_vocabularies(vocabularies, overlay_name=overlay)
                if vocabularies
                else None
            ),
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
        None,
        help="Publisher IRI for the DCAT catalog (default: did:web of base URL host)",
    ),
    publisher_name: str = typer.Option(
        "Dataspace Provider", help="Publisher display name"
    ),
    dsp_endpoint: str = typer.Option(
        None,
        help=(
            "DSP protocol URL that serves these datasets. Emitted as the "
            "catalogue's dcat:DataService (DSSC-PUB-41). Omitted when unset — "
            "the catalogue says nothing rather than guessing an endpoint."
        ),
    ),
    participant_did: str = ParticipantDidOpt,
    owners: Path = OwnersOpt,
    participants: Path = ParticipantsOpt,
    identity_registry_url: str = IdentityRegistryOpt,
    token: str = TokenOpt,
    profile: Path = ProfileOpt,
    overlay: str = OverlayOpt,
    sharing_offers: Path = SharingOffersOpt,
    deny_key: list[str] = DenyKeyOpt,
) -> None:
    """Validate, then write DCAT-AP catalog and ODRL offers as audit evidence."""
    odrl_profile = load_odrl_profile(profile) if profile else None
    owner_lookup, participant_dids, closers = _resolve_registries(
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
        service_endpoint=dsp_endpoint,
    )
    write_artifacts(result, catalog, offers, out_dir, profile=mapper.profile, name=name)

    _emit(result, "text")
    raise typer.Exit(0 if result.passed else 1)


@app.command("collect-offers")
def collect_offers(
    pattern: str = typer.Argument(
        ..., help="Glob matching sharing-offers.yaml files to collect"
    ),
    out_dir: Path = typer.Option(
        ..., "--out-dir", "-o", help="Target directory (e.g. sharing-offers.d/)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Collect sharing-offers.yaml from pipeline apps into sharing-offers.d/.

    Scans for sharing-offers.yaml files matching PATTERN (use recursive globs),
    loads each with its per-app overlay if present, and writes the result to
    OUT_DIR/<app>.yaml where <app> is the parent directory name.

    The overlay convention matches the runtime: a file named
    sharing-offers.<app>.yaml beside sharing-offers.yaml is loaded as a
    deployment overlay (replace-by-offer-id).

    Existing *.yaml files in OUT_DIR are removed first so that apps deleted
    since the last run do not leave stale contributions behind.
    """
    from glob import glob as globfn

    import yaml

    from .sharing import load_sharing_offers

    matches = sorted(globfn(pattern, recursive=True))
    if not matches:
        typer.echo(f"No files matched: {pattern}", err=True)
        raise typer.Exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.yaml"):
        old.unlink()

    collected = 0
    for match_str in matches:
        source = Path(match_str)
        app_name = source.parent.name

        catalogue = load_sharing_offers(source, overlay_name=app_name)
        if not catalogue.offers:
            if verbose:
                typer.echo(f"  skip {app_name} (no offers)")
            continue

        data = {
            "sharing_offers": [
                offer.model_dump(exclude_none=True) for offer in catalogue.offers
            ]
        }
        dest = out_dir / f"{app_name}.yaml"
        dest.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        collected += 1

        if verbose:
            overlay_applied = any(s != source.name for s in catalogue.sources.values())
            note = " (with overlay)" if overlay_applied else ""
            typer.echo(
                f"  {app_name}{note} → {dest.name} "
                f"({len(catalogue.offers)} offer{'s' if len(catalogue.offers) != 1 else ''})"
            )

    typer.echo(f"Collected {collected} sharing-offers file(s) into {out_dir}")


@app.command("fetch-vocabularies")
def fetch_vocabularies(
    file: Path = typer.Option(
        Path("vocabularies.yaml"), "--file", "-f", help="Path to vocabularies.yaml"
    ),
    cache_dir: Path = typer.Option(
        ..., "--cache-dir", help="Directory the JSON-LD copies are written to"
    ),
    # Not `OverlayOpt` — that one's help says `governance.<name>.yaml`, and this
    # command loads `vocabularies.<name>.yaml`. A shared option object whose text
    # names the wrong file is worse than a duplicated line.
    overlay: str | None = typer.Option(
        None,
        "--overlay",
        help="Deployment overlay name (loads vocabularies.<name>.yaml)",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Re-fetch entries that are already cached. Off by default: a cached "
        "copy is what the deployment is serving, and replacing it changes what a "
        "running catalogue's dct:conformsTo IRIs resolve to.",
    ),
) -> None:
    """Fill the local cache for every registered semantic vocabulary.

    The connector does this at startup too, and refuses to boot when it cannot —
    this command exists so an operator can do it deliberately, see the failures
    all at once, and refresh on purpose rather than by restarting.
    """
    from .vocabulary_cache import VocabularyFetchError, ensure_cached, status

    registry = load_vocabularies(file, overlay_name=overlay)
    if not registry.vocabularies:
        typer.echo(f"No vocabularies registered in {file} — nothing to fetch.")
        return

    try:
        written = ensure_cached(cache_dir, registry, refresh=refresh)
    except VocabularyFetchError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    for entry in status(cache_dir, registry):
        mark = "cached" if entry.cached else "MISSING"
        typer.echo(f"  {entry.slug}: {mark} → {entry.path}")
    typer.echo(f"{len(registry.vocabularies)} registered, {len(written)} fetched now.")


def main() -> None:
    sys.exit(app())


if __name__ == "__main__":
    main()
