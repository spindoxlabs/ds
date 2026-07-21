"""Pre-import validation for a governance file.

These checks validate *input* — the governance YAML and the registries it
references — so a bad file is caught before ``POST /provider/sync`` pushes it
into an EDC.  They deliberately do **not** re-assert properties of
``GovernanceMapper``'s output; that is unit-test territory (see
``tests/test_mapper.py``).  What is checked here cannot be known from the
mapper alone:

- collisions in the EDC identifiers derived from dataset keys (import-breaking)
- referential integrity against the owners / participant registries
- coherence of a rule's own declarations (consent, retention, validity window)
- deployment policy (dataset keys that must not reach a given environment)

Nothing here is specific to a deployment, a domain, or a dataset naming scheme;
every input is a parameter.
"""
from __future__ import annotations

import fnmatch
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

from ..mapper import GovernanceMapper
from ..models import GovernanceRuleV2
from ..resolver import GovernanceResolver

ACCESS_LEVELS = {"open", "internal", "restricted", "secret"}
CLASSIFICATIONS = {"pii", "green", "yellow", "red"}

CHECKS = (
    "governance-file",
    "access-level",
    "classification",
    "asset-id-collision",
    "policy-id-collision",
    "data-address",
    "consent-coherence",
    "retention",
    "validity-window",
    "owner-declared",
    "owner-resolvable",
    "owner-participant",
    "key-policy",
)


class OwnerLookup(Protocol):
    """Minimal owner-resolution surface.

    Satisfied by ``OwnersRegistry`` (YAML seed) and by the thin adapter over
    ``HttpOwnersRegistry`` in ``runtime.py`` (live identity-registry), so the
    same checks run offline or against a deployment.
    """

    def by_id(self, owner_id: str) -> Any | None: ...

    def all(self) -> list[Any]: ...


@dataclass
class Finding:
    check: str
    message: str
    dataset: str | None = None

    def asdict(self) -> dict[str, str]:
        data = {"check": self.check, "message": self.message}
        if self.dataset:
            data["dataset"] = self.dataset
        return data


@dataclass
class ValidationResult:
    governance_path: str
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    datasets_checked: int = 0
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    checks: list[str] = field(default_factory=lambda: list(CHECKS))
    artifacts: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors

    def error(self, check: str, message: str, dataset: str | None = None) -> None:
        self.errors.append(Finding(check, message, dataset))

    def warning(self, check: str, message: str, dataset: str | None = None) -> None:
        self.warnings.append(Finding(check, message, dataset))

    def asdict(self) -> dict[str, Any]:
        return {
            "governance_path": self.governance_path,
            "generated_at": self.generated_at,
            "passed": self.passed,
            "datasets_checked": self.datasets_checked,
            "checks": self.checks,
            "artifacts": self.artifacts,
            "errors": [item.asdict() for item in self.errors],
            "warnings": [item.asdict() for item in self.warnings],
        }


@dataclass(frozen=True)
class DatasetEvidence:
    """A resolved, exposed dataset together with its derived EDC identifiers."""

    key: str
    rule: GovernanceRuleV2
    asset_id: str
    policy_id: str
    contract_id: str


def load_exposed(
    resolver: GovernanceResolver, mapper: GovernanceMapper
) -> list[DatasetEvidence]:
    """Resolve every source key and keep the ones a sync would actually push."""
    evidence: list[DatasetEvidence] = []
    for key in resolver.config.sources:
        rule = resolver.resolve(key)
        if not rule.dataspace.expose or rule.access_level == "secret":
            continue
        asset_create = mapper.to_asset_create(key, rule)
        policy_create = mapper.to_policy_create(key, rule)
        contract = mapper.to_contract_definition(
            key, rule, policy_create["@id"], asset_create["@id"]
        )
        evidence.append(
            DatasetEvidence(
                key=key,
                rule=rule,
                asset_id=asset_create["@id"],
                policy_id=policy_create["@id"],
                contract_id=contract["@id"],
            )
        )
    return evidence


# ── Individual checks ────────────────────────────────────────────────────────


def check_enums(result: ValidationResult, exposed: list[DatasetEvidence]) -> None:
    for item in exposed:
        level = item.rule.access_level
        if level is not None and level not in ACCESS_LEVELS:
            result.error(
                "access-level",
                f"Unknown access_level '{level}' (expected one of {sorted(ACCESS_LEVELS)})",
                item.key,
            )
        classification = item.rule.classification
        if classification is not None and classification not in CLASSIFICATIONS:
            result.warning(
                "classification",
                f"Unrecognized classification '{classification}' "
                f"(known: {sorted(CLASSIFICATIONS)})",
                item.key,
            )


def check_identifier_collisions(
    result: ValidationResult, exposed: list[DatasetEvidence]
) -> None:
    """Two dataset keys must not derive the same EDC asset/policy/contract id.

    The mapper builds ids by substituting ``.`` with ``-`` or ``/``, so keys
    that differ only in those separators silently overwrite each other on sync.
    """
    for check, attr, label in (
        ("asset-id-collision", "asset_id", "asset id"),
        ("policy-id-collision", "policy_id", "policy id"),
        ("policy-id-collision", "contract_id", "contract id"),
    ):
        by_id: dict[str, list[str]] = defaultdict(list)
        for item in exposed:
            by_id[getattr(item, attr)].append(item.key)
        for identifier, keys in sorted(by_id.items()):
            if len(keys) > 1:
                result.error(
                    check,
                    f"Datasets {', '.join(sorted(keys))} all derive {label} '{identifier}'",
                )


def check_data_address(result: ValidationResult, exposed: list[DatasetEvidence]) -> None:
    for item in exposed:
        address = item.rule.dataspace.data_address
        base_url = (address.base_url or "").strip()
        if not base_url:
            result.error("data-address", "Exposed dataset has no data_address.base_url", item.key)
            continue
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            result.error(
                "data-address",
                f"data_address.base_url is not an absolute URL: '{base_url}'",
                item.key,
            )
        elif parsed.scheme not in ("http", "https"):
            result.error(
                "data-address",
                f"data_address.base_url must be http(s), got '{parsed.scheme}'",
                item.key,
            )


def check_consent_coherence(
    result: ValidationResult, exposed: list[DatasetEvidence]
) -> None:
    """A dataset's consent declarations must agree with its row-filtering setup."""
    for item in exposed:
        rule = item.rule
        has_filter = bool(rule.user_filter_column or rule.row_filters)
        if rule.policy.consent.required and not has_filter:
            result.warning(
                "consent-coherence",
                "consent.required is set but no user_filter_column or row_filters "
                "are declared — consent cannot be enforced per subject",
                item.key,
            )
        if rule.classification == "pii" and not has_filter:
            result.warning(
                "consent-coherence",
                "Dataset is classified 'pii' but declares no row-level filtering",
                item.key,
            )
        for row_filter in rule.row_filters:
            if not row_filter.args.column.strip():
                result.error(
                    "consent-coherence",
                    f"row_filter '{row_filter.handler}' has an empty column",
                    item.key,
                )


def check_retention(result: ValidationResult, exposed: list[DatasetEvidence]) -> None:
    for item in exposed:
        for label, value in (
            ("retention_days", item.rule.retention_days),
            ("policy.obligations.delete_after_days", item.rule.policy.obligations.delete_after_days),
        ):
            if value is not None and value <= 0:
                result.error(
                    "retention", f"{label} must be positive, got {value}", item.key
                )


def check_validity_window(
    result: ValidationResult, exposed: list[DatasetEvidence]
) -> None:
    for item in exposed:
        policy = item.rule.policy
        if policy.valid_from and policy.valid_until and policy.valid_from > policy.valid_until:
            result.error(
                "validity-window",
                f"policy.valid_from ({policy.valid_from}) is after "
                f"policy.valid_until ({policy.valid_until})",
                item.key,
            )


def check_owners(
    result: ValidationResult,
    exposed: list[DatasetEvidence],
    owners: OwnerLookup | None,
    participant_dids: set[str] | None,
) -> None:
    """Referential integrity between governance ownership and the registries."""
    aliases: dict[str, str] = {}
    for item in exposed:
        if not item.rule.ownership:
            result.warning(
                "owner-declared",
                "Exposed dataset declares no ownership — ODRL assigner falls back "
                "to the participant DID",
                item.key,
            )
        for owner in item.rule.ownership:
            aliases.setdefault(owner.name, item.key)

    if owners is None:
        return

    for alias, dataset_key in sorted(aliases.items()):
        if not owners.by_id(alias):
            result.error(
                "owner-resolvable",
                f"Ownership alias '{alias}' does not resolve in the owners registry",
                dataset_key,
            )

    if not participant_dids:
        return
    for entry in owners.all():
        did = getattr(entry, "did", None)
        if did and did not in participant_dids:
            result.warning(
                "owner-participant",
                f"Owner '{getattr(entry, 'id', '?')}' DID '{did}' is not a registered participant",
            )


def check_key_policy(
    result: ValidationResult, exposed: list[DatasetEvidence], deny_patterns: list[str]
) -> None:
    """Reject dataset keys that must not be exposed in the target environment.

    Generalizes the old hardcoded "core profile must not expose dev datasets"
    rule — the caller supplies the glob patterns.
    """
    for pattern in deny_patterns:
        matched = sorted(
            item.key for item in exposed if fnmatch.fnmatch(item.key, pattern)
        )
        if matched:
            result.error(
                "key-policy",
                f"Dataset keys matching denied pattern '{pattern}' are exposed: "
                + ", ".join(matched),
            )
