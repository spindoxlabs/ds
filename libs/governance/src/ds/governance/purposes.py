"""Whether a dataset's declared purposes are usable at all.

**One predicate, two gates.** `check_dataset_purposes` runs it offline in
`task compliance:validate`; the connector's `sync_governance` runs it at ingest.
Two implementations of "is this purpose usable" would drift, and each would look
correct in isolation — the CLI passing a file the sync then refuses is the mild
version; the sync passing one the CLI would have caught is the bad one.

The rule mirrors `GovernanceMapper._purpose_iris` deliberately: the point is to
name exactly what the mapper would otherwise drop in silence.
"""

from __future__ import annotations

from .models import GovernanceRuleV2, OdrlProfile


def unresolved_purposes(purposes: list[str], profile: OdrlProfile) -> list[str]:
    """The entries this profile cannot resolve, in declaration order.

    An entry is usable when it resolves to a taxonomy slug, or when it is an
    absolute IRI — a deployment may legitimately declare a purpose from a
    vocabulary this profile does not carry, and the mapper passes those through.
    """
    return [
        entry
        for entry in purposes
        if profile.purpose_slug(entry) is None and "://" not in entry
    ]


def purpose_failure(rule: GovernanceRuleV2, profile: OdrlProfile) -> str | None:
    """Why this rule's purposes are unusable, or ``None`` when they are fine.

    An **empty** ``dataspace.purpose[]`` fails as surely as an unresolvable one.
    `_build_permission` emits a purpose constraint only for a non-empty list, so
    both end as an offer published with no purpose limitation whatsoever — and
    the empty case used to pass every check in this repo, because the checks
    iterated the entries and an empty list has none.
    """
    declared = rule.dataspace.purpose
    if not declared:
        return (
            "declares no purpose — it would be published with no purpose "
            "constraint, so nothing would limit what a consumer may use it for"
        )

    unresolved = unresolved_purposes(declared, profile)
    if unresolved:
        listed = ", ".join(repr(entry) for entry in unresolved)
        known = (
            ", ".join(sorted(profile.purpose_index)) or "(the profile declares none)"
        )
        return (
            f"declares {listed}, which the ODRL profile taxonomy does not "
            f"define — the constraint would be dropped and the dataset "
            f"published unrestricted. Known purposes: {known}"
        )

    return None
