"""Top-level governance validation — the pre-import gate."""
from __future__ import annotations

from pathlib import Path

import yaml

from ..mapper import GovernanceMapper
from ..models import OdrlProfile, load_odrl_profile
from ..resolver import GovernanceResolver
from ..sharing import DuplicateOfferError, SharingOfferCatalogue, load_sharing_offers
from ..vocabularies import VocabularyRegistry
from .checks import (
    CHECKS,
    OwnerLookup,
    ValidationResult,
    check_consent_coherence,
    check_data_address,
    check_enums,
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
    RoleLookup,
    check_dataset_purposes,
    check_purpose_taxonomy,
    check_sharing_offers,
)


def _read_participants(path: Path | None) -> list[dict] | None:
    """Load the ``participants:`` list from a seed, or ``None`` if none was asked for.

    **A path that was given and cannot be read is an error, not an absence.**
    Both participant lookups are optional by design — an offline run with no seed
    downgrades `owner-participant` and `controller_role` to warnings and carries
    on. That is correct when the caller *said nothing*. It is a silent hole when
    the caller named a file and the file is not there: the run reports PASS
    having skipped exactly the checks it was invoked to perform.

    This is not hypothetical. `.github/workflows/compliance.yml` passed
    `--participants services/connector/governance/participants.yaml` from the
    commit that **deleted** that file (`5484ff0`) until this check existed, and
    every CI run since was green with both checks unexecuted.
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


def load_participant_roles(path: Path | None) -> dict[str, list[str]] | None:
    """Read ``did -> roles`` from a participants.yaml seed."""
    entries = _read_participants(path)
    if entries is None:
        return None
    return {entry["id"]: list(entry.get("roles") or []) for entry in entries}


def build_role_lookup(
    catalogue: SharingOfferCatalogue,
    owners: OwnerLookup | None,
    participant_roles: dict[str, list[str]] | None,
) -> RoleLookup | None:
    """Resolve each offer's controller alias to the roles that participant holds.

    Owner aliases and participant roles live in two different tables, joined by
    the owner's DID.  When the owners registry is unavailable there is nothing
    to check against, so the caller gets ``None`` and the controller check
    downgrades to a warning rather than failing an offline run.
    """
    if owners is None:
        return None
    roles_by_alias: dict[str, list[str]] = {}
    for offer in catalogue.offers:
        alias = offer.recipients.controller
        if alias in roles_by_alias:
            continue
        entry = owners.by_id(alias)
        if entry is None:
            continue
        did = getattr(entry, "did", None)
        roles_by_alias[alias] = list((participant_roles or {}).get(did) or [])
    return RoleLookup(roles_by_alias)


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
    participant_roles: dict[str, list[str]] | None = None,
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
    too: the purpose taxonomy, each dataset's ``policy.purpose[]``, and every
    offer's purpose, datasets, controller, legal basis and codes.
    """
    result = ValidationResult(governance_path=str(governance_path))
    result.checks = list(CHECKS) + list(CONSENT_CHECKS)

    if not governance_path.exists():
        result.error("governance-file", f"Missing governance file: {governance_path}")
        return result

    try:
        resolver = GovernanceResolver.from_file_with_override(
            governance_path, overlay_name=overlay_name
        )
    except yaml.YAMLError as exc:
        result.error("governance-file", f"Governance file is not valid YAML: {exc}")
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
    check_data_address(result, exposed)
    check_consent_coherence(result, exposed)
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
    try:
        catalogue = load_sharing_offers(sharing_offers_path, overlay_name=overlay_name)
    except DuplicateOfferError as exc:
        result.error("offer-duplicate", str(exc))
        return result

    if catalogue.offers:
        check_sharing_offers(
            result,
            catalogue,
            exposed,
            active_profile,
            build_role_lookup(catalogue, owners, participant_roles),
        )
        result.offers_checked = len(catalogue.offers)

    return result
