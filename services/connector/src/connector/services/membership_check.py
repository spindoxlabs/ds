"""Check organization membership via identity-registry API."""

from __future__ import annotations

import enum
import logging
from pathlib import Path

import httpx
from ds.governance.resolver import GovernanceResolver

log = logging.getLogger(__name__)


class Membership(enum.Enum):
    """Whether a subject belongs to an organisation, and the third answer.

    ``MEMBER`` and ``NOT_MEMBER`` are claims about the person. ``UNKNOWN`` is a
    claim about *us*: the registry could not be reached, refused our credentials,
    or answered something we could not read.

    It is a distinct value because collapsing it into ``NOT_MEMBER`` — which is
    what returning a bare ``bool`` forced — makes an outage indistinguishable
    from somebody who never joined. An authorization gate then refuses a member
    with a ``403`` asserting a fact that was never established, and the caller,
    told plainly that the person is not a member, files a permanent failure for
    something a retry would have fixed.

    Callers must map ``UNKNOWN`` to a retryable failure rather than a denial.
    Matching on the enum, rather than testing it for truthiness, is what keeps
    that decision from being made by accident: every value is truthy.
    """

    MEMBER = "member"
    NOT_MEMBER = "not_member"
    UNKNOWN = "unknown"


async def check_subject_membership(
    identity_registry_url: str,
    user_did: str,
    organization_alias: str,
    token_provider=None,
) -> Membership:
    """Ask the registry whether *user_did* belongs to *organization_alias*.

    Every log line here names the **organisation as well as the subject**. The
    membership API compares ``organization`` as a literal string, so the failure
    this check is most likely to report is a caller asking under a name the row
    was not written under — two spellings of one organisation, a governance file
    and a realm that disagree. A message naming only the subject describes that
    as a fact about the person and sends the reader looking in the wrong place.
    """
    headers = {}
    if token_provider:
        try:
            token = await token_provider()
        except Exception as exc:  # noqa: BLE001 — an unmintable token is not a denial
            log.error(
                "Could not mint a token to check membership of %s in %r: %s",
                user_did,
                organization_alias,
                exc,
            )
            return Membership.UNKNOWN
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(
            base_url=identity_registry_url.rstrip("/"), timeout=10.0
        ) as client:
            resp = await client.get(
                "/memberships/check",
                params={"user_did": user_did, "organization": organization_alias},
                headers=headers,
            )
    except httpx.HTTPError as exc:
        log.error(
            "Identity registry unreachable checking membership of %s in %r: %s",
            user_did,
            organization_alias,
            exc,
        )
        return Membership.UNKNOWN

    if resp.status_code in (401, 403):
        # Ours, not theirs: the registry declined *this service's* credentials.
        log.error(
            "Identity registry refused our credentials (%d) checking membership "
            "of %s in %r — this is a connector misconfiguration, not a subject "
            "who is not a member",
            resp.status_code,
            user_did,
            organization_alias,
        )
        return Membership.UNKNOWN

    if resp.status_code != 200:
        log.error(
            "Identity registry answered %d checking membership of %s in %r",
            resp.status_code,
            user_did,
            organization_alias,
        )
        return Membership.UNKNOWN

    try:
        member = resp.json().get("member")
    except ValueError as exc:
        log.error(
            "Identity registry returned an unreadable body checking membership "
            "of %s in %r: %s",
            user_did,
            organization_alias,
            exc,
        )
        return Membership.UNKNOWN

    if not isinstance(member, bool):
        # An absent or non-boolean `member` is a contract the registry did not
        # keep. Reading it as False would deny on a shape we do not understand.
        log.error(
            "Identity registry omitted a boolean 'member' checking membership "
            "of %s in %r",
            user_did,
            organization_alias,
        )
        return Membership.UNKNOWN

    if not member:
        log.info(
            "Subject %s is not a member of %r according to the identity registry",
            user_did,
            organization_alias,
        )
    return Membership.MEMBER if member else Membership.NOT_MEMBER


def resolve_dataset_owner(
    governance_yaml_path: str,
    dataset_id: str,
    overlay_name: str | None = None,
) -> str | None:
    """Resolve the first ownership alias for a dataset from governance config."""
    path = Path(governance_yaml_path)
    resolver = GovernanceResolver.from_file_with_override(
        path, overlay_name=overlay_name
    )
    rule = resolver.resolve(dataset_id)
    if rule.ownership:
        return rule.ownership[0].name
    return None
