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
from ..vocabularies import VocabularyRegistry

ACCESS_LEVELS = {"open", "internal", "restricted", "secret"}
CLASSIFICATIONS = {"pii", "green", "yellow", "red"}

CHECKS = (
    "governance-file",
    "access-level",
    "classification",
    "asset-id-collision",
    "policy-id-collision",
    "policy-contract-id-collision",
    "declared-not-enforced",
    "dcat-ap",
    "data-address",
    "consent-coherence",
    "retention",
    "validity-window",
    "owner-declared",
    "owner-resolvable",
    "owner-participant",
    "key-policy",
    "semantic-model",
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
    offers_checked: int = 0
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
            "offers_checked": self.offers_checked,
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


def check_policy_contract_id_collision(
    result: ValidationResult, exposed: list[DatasetEvidence]
) -> None:
    """One dataset's policy id and contract id must differ (``GOV-12``).

    They are separate EDC collections, so nothing rejects the duplicate — the id
    just stops identifying which entity is meant, in logs, in evidence rows and
    in whatever an operator greps. Both used to derive from the single
    ``dataspace.contract.access_policy_id``, so naming the access policy was
    enough to collide them.
    """
    for item in exposed:
        if item.policy_id == item.contract_id:
            result.error(
                "policy-contract-id-collision",
                f"policy and contract definition both derive @id '{item.policy_id}'. "
                "Set dataspace.contract.contract_definition_id, or leave both unset "
                "so the -policy/-contract suffixes apply.",
                item.key,
            )


#: Fields governance may declare that reach no emitter and no enforcement point.
#:
#: Each is parsed, merged through overlays and validated, and then read by
#: nothing — so a producer who sets one has stated an intention this platform
#: does not act on, and nothing has ever said so. `DSSC-AUP-06` forbids showing
#: a counterparty a term that is not enforced; the same argument applies inward,
#: to the producer who wrote it.
#:
#: **Warnings, not errors** (`GOV-13`, `GOV-14`). The declaration is not invalid
#: — it is unimplemented, which is the platform's gap and not the file's — and a
#: hard failure would block a deployment over a field that has been accepted for
#: as long as it has existed.
#:
#: The alternative was deleting the fields. That is worse: it turns "we do not do
#: this yet" into silence, and the next producer re-adds the key expecting it to
#: work. Wiring one is what closes its line here.
UNENFORCED_DECLARATIONS: tuple[tuple[str, str, str], ...] = (
    (
        "policy.valid_from",
        "policy.valid_from",
        "no ODRL constraint is emitted for it and no enforcement point reads it; "
        "the value is order-checked against valid_until and nothing else",
    ),
    (
        "policy.valid_until",
        "policy.valid_until",
        "no ODRL constraint is emitted for it and no enforcement point reads it; "
        "an offer does not expire",
    ),
    (
        "policy.obligations.notify_on_access",
        "policy.obligations.notify_on_access",
        "no notification is sent on access",
    ),
    (
        "policy.obligations.anonymize_before_use",
        "policy.obligations.anonymize_before_use",
        "no anonymisation is applied; the data plane returns the rows the row "
        "filter selects, unchanged",
    ),
)


def _declared_value(rule: object, dotted: str) -> object:
    node: object = rule
    for part in dotted.split("."):
        node = getattr(node, part, None)
        if node is None:
            return None
    return node


def check_declared_not_enforced(
    result: ValidationResult, exposed: list[DatasetEvidence]
) -> None:
    """Warn on a governance field this platform parses and does not act on."""
    for item in exposed:
        for label, dotted, consequence in UNENFORCED_DECLARATIONS:
            if _declared_value(item.rule, dotted):
                result.warning(
                    "declared-not-enforced",
                    f"{label} is declared, and this platform does not enforce it: "
                    f"{consequence}.",
                    item.key,
                )


#: DCAT-AP properties, by obligation, on the `dcat:Dataset` this platform emits.
#:
#: Only those whose value comes from **governance** are listed. `dct:identifier`,
#: `dct:publisher` and `dcat:distribution` are synthesised by the emitter from
#: the asset id, the participant and the data address, so a governance file
#: cannot omit them and a check on them would test the emitter, not the input —
#: which is the boundary the module docstring above draws.
_DCAT_AP_MANDATORY: tuple[tuple[str, str, str], ...] = (
    ("dct:title", "title", "the dataset key is used as a title, which is an identifier"),
    ("dct:description", "description", "the dataset is published with an empty description"),
)

_DCAT_AP_RECOMMENDED: tuple[tuple[str, str, str], ...] = (
    ("dcat:theme", "dcat.themes", "the dataset appears under no theme in a harvester"),
    ("dct:license", "license", "a consumer cannot tell what they may do with the data"),
    ("dct:accrualPeriodicity", "dcat.accrual_periodicity", "how often it updates is unstated"),
    ("dct:spatial", "dcat.spatial_uris", "the geographic coverage is unstated"),
    ("dct:temporal", "dcat.temporal", "the time span covered is unstated"),
)


def check_dcat_ap(result: ValidationResult, exposed: list[DatasetEvidence]) -> None:
    """DCAT-AP conformance of the metadata this file will publish (``GOV-07``).

    Rulebook `C-12` / `DSSC-DSO-11`: *metadata is checked for compliance with the
    standards it claims*, recorded there as an open gap — `ds-governance
    validate` checked internal coherence and referential integrity, and nothing
    checked the thing the catalogue is actually judged as.

    **Mandatory properties are errors, recommended ones are warnings**, which is
    DCAT-AP's own distinction rather than a severity we chose. The mandatory two
    both have fallbacks in the emitter, and that is exactly why they need a check
    here: `dct:title` falls back to the dataset key and `dct:description` to
    `""`, so a dataset with neither publishes a *structurally valid* DCAT record
    that tells a consumer nothing. A validator that only looked at the emitted
    shape would pass it.
    """
    for item in exposed:
        for prop, source, consequence in _DCAT_AP_MANDATORY:
            if not _declared_value(item.rule, source):
                result.error(
                    "dcat-ap",
                    f"{prop} is mandatory in DCAT-AP and governance declares no "
                    f"'{source}' — {consequence}",
                    item.key,
                )
        for prop, source, consequence in _DCAT_AP_RECOMMENDED:
            if not _declared_value(item.rule, source):
                result.warning(
                    "dcat-ap",
                    f"{prop} is recommended in DCAT-AP and governance declares no "
                    f"'{source}' — {consequence}",
                    item.key,
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

    # `is None`, not falsy. `None` is "no participant list was asked for" and
    # skipping is correct; `set()` is "asked, and the registry has nobody
    # enrolled", where every owner with a DID is unregistered and every one of
    # them is a finding. Reading the two the same way is how this check reported
    # conformity against an empty registry — the shape `CI-02` and `GOV-19` are
    # both instances of.
    if participant_dids is None:
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


def check_semantic_model(
    result: ValidationResult,
    exposed: list[DatasetEvidence],
    registry: "VocabularyRegistry | None" = None,
) -> None:
    """`dcat.conforms_to` — the payload semantic model (rulebook `M-4`, `M-7`).

    Two findings at two severities, and the split is the whole design.

    **A non-absolute URI is an error.** `M-7`: *"an offering's declared model must
    be resolvable — a bare name is not a model reference"*. `saref4ener` names
    nothing a consumer can dereference; publishing it into `dct:conformsTo` puts a
    string that looks like a standard reference into the catalogue and is not one.
    This is the check that makes `M-7` enforceable rather than merely declared.

    **An absolute URI with no registered local copy is a warning.** An external
    standard IRI is a legitimate reference whether or not this deployment mirrors
    it — refusing here would force every participant to cache SAREF before it
    could say a dataset conforms to SAREF, which inverts what the registry is for.
    The warning exists because the *usual* cause is a typo or a registry entry
    somebody forgot, and silence would make those indistinguishable from intent.

    A dataset declaring **no** model is not reported at all. The platform is
    domain-agnostic and mandates no payload model (`M-6`); requiring one here
    would be this repository imposing a decision the rulebook gives a deployment.
    """
    for item in exposed:
        declared = item.rule.dcat.conforms_to
        if not declared:
            continue

        parsed = urlparse(declared.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            result.error(
                "semantic-model",
                f"dcat.conforms_to '{declared}' is not an absolute http(s) URI — "
                "a bare name is not a model reference (M-7)",
                item.key,
            )
            continue

        if registry is not None and registry.resolve(declared) is None:
            result.warning(
                "semantic-model",
                f"dcat.conforms_to '{declared}' is not in the vocabulary registry, "
                "so this participant serves no local copy of it. Register it to "
                "publish it at /ns/{slug}, or leave it if the IRI is meant to "
                "resolve elsewhere.",
                item.key,
            )
