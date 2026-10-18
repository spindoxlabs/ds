"""Top-level governance validation — the pre-import gate."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml
from celine.governance.check import ERROR, WARNING, check_governance

from ..mapper import GovernanceMapper
from ..models import OdrlProfile, load_odrl_profile
from ..resolver import GovernanceResolver
from ..sharing import (
    ConflictingRecipientRolesError,
    DuplicateOfferError,
    SharingOfferCatalogue,
    load_sharing_offers,
)
from ..vocabularies import VocabularyRegistry
from .checks import (
    CHECKS,
    OwnerLookup,
    ValidationResult,
    check_consent_coherence,
    check_exposure_conflict,
    check_data_address,
    check_dcat_ap,
    check_policy_contract_id_collision,
    check_enums,
    check_declared_not_enforced,
    check_identifier_collisions,
    check_key_policy,
    check_owners,
    check_retention,
    check_semantic_model,
    check_validity_window,
    load_exposed,
)
from .consent_checks import (
    CONSENT_CHECKS,
    RecipientLookup,
    check_dataset_purposes,
    check_purpose_taxonomy,
    check_sharing_offers,
)


def _read_participants(path: Path | None) -> list[dict[str, Any]] | None:
    """Load the ``participants:`` list from a seed, or ``None`` if none was asked for.

    **A path that was given and cannot be read is an error, not an absence.**
    The participant lookup is optional by design — an offline run with no seed
    downgrades `owner-participant` to a warning and carries on. That is correct
    when the caller *said nothing*. It is a silent hole when
    the caller named a file and the file is not there: the run reports PASS
    having skipped exactly the checks it was invoked to perform.

    This is not hypothetical. `.github/workflows/compliance.yml` passed
    `--participants services/connector/governance/participants.yaml` from the
    commit that **deleted** that file (`5484ff0`) until this check existed, and
    every CI run since was green with the check unexecuted.
    """
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(
            f"participants seed '{path}' does not exist. Omit --participants to "
            f"run without participant checks (they downgrade to warnings), or "
            f"point it at a real seed — but do not name a file that is not there: "
            f"the run would pass by skipping the checks you asked for."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        entry
        for entry in raw.get("participants", [])
        if isinstance(entry, dict) and entry.get("id")
    ]


def load_participant_dids(path: Path | None) -> set[str] | None:
    """Read participant DIDs from a participants.yaml seed."""
    entries = _read_participants(path)
    if entries is None:
        return None
    return {entry["id"] for entry in entries}


def build_recipient_lookup(
    catalogue: SharingOfferCatalogue,
    owners: OwnerLookup | None,
) -> RecipientLookup | None:
    """Which of the offers' recipient aliases resolve in the owners registry.

    When the owners registry is unavailable there is nothing to resolve against,
    so the caller gets ``None`` and the recipient check downgrades to a warning
    rather than failing an offline run.

    This used to also join each alias to that participant's DSP roles, to check
    ``recipient_role`` against them. It cannot: the registry pins participant
    roles to ``{provider, consumer}`` and a ``recipient_role`` is a controller
    *function*. The vocabulary is declared beside the offers now, so this
    function no longer reads participants at all.
    """
    if owners is None:
        return None
    known = {
        offer.recipients.recipient
        for offer in catalogue.offers
        if owners.by_id(offer.recipients.recipient) is not None
    }
    return RecipientLookup(known)


#: The name this helper carried before the recipient rename (2026-09-17). Kept as
#: an alias because `ds.governance.compliance` is a published surface.
build_controller_lookup = build_recipient_lookup


#: What `celine.governance.check` contributes, as ds reports it: its rule names
#: under one prefix, so a reader can tell the platform's rules from ds's own.
UPSTREAM_CHECKS = (
    "governance-schema",
    "governance-row-policy",
    "governance-handler",
    "governance-layer-verdict",
)

#: Upstream rules ds does not repeat. `consent-coherence` is ds's own check,
#: ported upstream (celine-utils rule 5); ds keeps the original, which has arms
#: the port does not, and reporting both would say every finding twice.
_UPSTREAM_SKIPPED = frozenset({"consent-coherence"})


def check_upstream(
    result: ValidationResult, governance_path: Path, overlay_name: str | None
) -> None:
    """Run `celine.governance.check` over the file exactly as ds will read it.

    The platform's rules first (celine-utils ≥ 2.7): the published JSON schema
    with unknown keys, the two-layer row policy, the handler names and the layer
    verdicts — on the **materialized** file, base plus the overlay ds merges.

    Run on a copy because the two resolve the overlay differently: ds takes the
    name given or `GOVERNANCE_OVERLAY_NAME`, upstream's checker the variable or
    the name of the directory holding the file. Copied into a directory named
    after ds's overlay (or a name no overlay has), upstream merges exactly the
    overlay ds merges, never a neighbour ds would not read. Findings name the
    original files. Deployment plugins are not known here, so a handler finding
    for one is upstream's, reported as it reports it.
    """
    name = overlay_name or os.getenv("GOVERNANCE_OVERLAY_NAME")
    overlay = governance_path.parent / f"governance.{name}.yaml" if name else None
    with tempfile.TemporaryDirectory(prefix="ds-governance-") as scratch:
        directory = Path(scratch) / (name or "_no_overlay_")
        directory.mkdir()
        copies = {directory / "governance.yaml": governance_path}
        shutil.copyfile(governance_path, directory / "governance.yaml")
        if overlay is not None and overlay.is_file():
            target = directory / f"governance.{name}.yaml"
            shutil.copyfile(overlay, target)
            copies[target] = overlay
        report = check_governance([directory / "governance.yaml"])

    originals = {str(copy): str(original) for copy, original in copies.items()}
    for finding in report.findings:
        if finding.rule in _UPSTREAM_SKIPPED:
            continue
        source = originals.get(finding.source, finding.source)
        message = f"{finding.detail} ({source})"
        check = f"governance-{finding.rule}"
        if finding.severity == ERROR:
            result.error(check, message, finding.dataset)
        elif finding.severity == WARNING:
            result.warning(check, message, finding.dataset)


def validate(
    governance_path: Path,
    *,
    participant_id: str,
    base_url: str,
    participant_did: str | None = None,
    owners: OwnerLookup | None = None,
    participant_dids: set[str] | None = None,
    profile: OdrlProfile | None = None,
    overlay_name: str | None = None,
    deny_key_patterns: list[str] | None = None,
    sharing_offers_path: Path | None = None,
    # The semantic vocabulary registry, when the caller has one. `None` means
    # "do not check registration" rather than "nothing is registered": the
    # difference is a warning that would otherwise fire on every dataset for a
    # caller that simply does not run a vocabulary registry.
    vocabularies: VocabularyRegistry | None = None,
) -> ValidationResult:
    """Validate a governance file as a deployable catalogue.

    Every environment-specific input — the participant identity, the owners
    registry, the denied key patterns — is a parameter, so the same validator
    runs against any governance file in any deployment.

    When *sharing_offers_path* is given, the consent vocabulary is validated
    too: the purpose taxonomy, each dataset's ``dataspace.purpose[]``, and every
    offer's purpose, datasets, recipient, legal basis and codes.
    """
    result = ValidationResult(governance_path=str(governance_path))
    result.checks = list(UPSTREAM_CHECKS) + list(CHECKS) + list(CONSENT_CHECKS)

    if not governance_path.exists():
        result.error("governance-file", f"Missing governance file: {governance_path}")
        return result

    check_upstream(result, governance_path, overlay_name)

    try:
        resolver = GovernanceResolver.from_file_with_override(
            governance_path, overlay_name=overlay_name
        )
    except yaml.YAMLError as exc:
        result.error("governance-file", f"Governance file is not valid YAML: {exc}")
        return result
    except ValueError as exc:
        # A malformed row filter, among others: the resolver refuses the file
        # rather than reading the entry as no filter. Reported, not raised — the
        # gate answers "which file, which entry", a traceback does not.
        result.error("governance-file", f"Governance file does not load: {exc}")
        return result

    if not resolver.config.sources:
        result.error("governance-file", "Governance file declares no sources")
        return result

    active_profile = profile or load_odrl_profile()
    mapper = GovernanceMapper(
        participant_id=participant_id,
        base_url=base_url,
        profile=active_profile,
        participant_did=participant_did,
    )
    exposed = load_exposed(resolver, mapper)
    result.datasets_checked = len(exposed)

    if not exposed:
        result.warning(
            "governance-file",
            f"No dataset is exposed — {len(resolver.config.sources)} source(s) declared, "
            "all either expose:false or access_level:secret",
        )
        return result

    check_enums(result, exposed)
    check_identifier_collisions(result, exposed)
    check_policy_contract_id_collision(result, exposed)
    check_declared_not_enforced(result, exposed)
    check_dcat_ap(result, exposed)
    check_data_address(result, exposed)
    check_consent_coherence(result, exposed)
    check_exposure_conflict(result, exposed)
    check_retention(result, exposed)
    check_validity_window(result, exposed)
    check_owners(result, exposed, owners, participant_dids)
    check_key_policy(result, exposed, deny_key_patterns or [])
    check_semantic_model(result, exposed, vocabularies)

    # ── Consent vocabulary ────────────────────────────────────────────────
    check_purpose_taxonomy(result, active_profile)
    check_dataset_purposes(result, exposed, active_profile)

    # A duplicate id is fatal to *loading* — with no baseline there is no winner
    # to pick — but the gate must report it like any other finding. A traceback
    # is a worse answer to "which file should I fix" than a named error.
    #
    # Two exceptions, two check codes. A conflicting unbundling is a recipient
    # finding, not a duplicate offer, and the code is what a machine filters on —
    # reporting it as `offer-duplicate` would send a reader looking for two offers
    # with one id.
    try:
        catalogue = load_sharing_offers(sharing_offers_path, overlay_name=overlay_name)
    except DuplicateOfferError as exc:
        result.error("offer-duplicate", str(exc))
        return result
    except ConflictingRecipientRolesError as exc:
        result.error("offer-recipient", str(exc))
        return result

    if catalogue.offers:
        check_sharing_offers(
            result,
            catalogue,
            exposed,
            active_profile,
            build_recipient_lookup(catalogue, owners),
        )
        result.offers_checked = len(catalogue.offers)

    return result
