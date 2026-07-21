"""Top-level governance validation — the pre-import gate."""
from __future__ import annotations

from pathlib import Path

import yaml

from ..mapper import GovernanceMapper
from ..models import OdrlProfile
from ..resolver import GovernanceResolver
from .checks import (
    OwnerLookup,
    ValidationResult,
    check_consent_coherence,
    check_data_address,
    check_enums,
    check_identifier_collisions,
    check_key_policy,
    check_owners,
    check_retention,
    check_validity_window,
    load_exposed,
)


def load_participant_dids(path: Path | None) -> set[str] | None:
    """Read participant DIDs from a participants.yaml seed."""
    if path is None or not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        entry["id"]
        for entry in raw.get("participants", [])
        if isinstance(entry, dict) and entry.get("id")
    }


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
) -> ValidationResult:
    """Validate a governance file as a deployable catalogue.

    Every environment-specific input — the participant identity, the owners
    registry, the denied key patterns — is a parameter, so the same validator
    runs against any governance file in any deployment.
    """
    result = ValidationResult(governance_path=str(governance_path))

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

    mapper = GovernanceMapper(
        participant_id=participant_id,
        base_url=base_url,
        profile=profile,
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

    return result
