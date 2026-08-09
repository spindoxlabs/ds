"""Top-level governance validation — the pre-import gate."""
from __future__ import annotations

from pathlib import Path

import yaml

from ..mapper import GovernanceMapper
from ..models import OdrlProfile, load_odrl_profile
from ..resolver import GovernanceResolver
from ..sharing import (
    ConflictingControllerRolesError,
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
    ControllerLookup,
    check_dataset_purposes,
    check_purpose_taxonomy,
    check_sharing_offers,
)


def _read_participants(path: Path | None) -> list[dict] | None:
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


def build_controller_lookup(
    catalogue: SharingOfferCatalogue,
    owners: OwnerLookup | None,
) -> ControllerLookup | None:
    """Which of the offers' controller aliases resolve in the owners registry.

    When the owners registry is unavailable there is nothing to resolve against,
    so the caller gets ``None`` and the controller check downgrades to a warning
    rather than failing an offline run.

    This used to also join each alias to that participant's DSP roles, to check
    ``controller_role`` against them. It cannot: the registry pins participant
    roles to ``{provider, consumer}`` and a ``controller_role`` is a controller
    *function*. The vocabulary is declared beside the offers now, so this
    function no longer reads participants at all.
    """
    if owners is None:
        return None
    known = {
        offer.recipients.controller
        for offer in catalogue.offers
        if owners.by_id(offer.recipients.controller) is not None
    }
    return ControllerLookup(known)


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
    check_policy_contract_id_collision(result, exposed)
    check_declared_not_enforced(result, exposed)
    check_dcat_ap(result, exposed)
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
    #
    # Two exceptions, two check codes. A conflicting unbundling is a controller
    # finding, not a duplicate offer, and the code is what a machine filters on —
    # reporting it as `offer-duplicate` would send a reader looking for two offers
    # with one id.
    try:
        catalogue = load_sharing_offers(sharing_offers_path, overlay_name=overlay_name)
    except DuplicateOfferError as exc:
        result.error("offer-duplicate", str(exc))
        return result
    except ConflictingControllerRolesError as exc:
        result.error("offer-controller", str(exc))
        return result

    if catalogue.offers:
        check_sharing_offers(
            result,
            catalogue,
            exposed,
            active_profile,
            build_controller_lookup(catalogue, owners),
        )
        result.offers_checked = len(catalogue.offers)

    return result
