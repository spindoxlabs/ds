"""Check organization membership via identity-registry API."""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from ds.governance.resolver import GovernanceResolver

log = logging.getLogger(__name__)


async def check_subject_membership(
    identity_registry_url: str,
    user_did: str,
    organization_alias: str,
    token_provider=None,
) -> bool:
    headers = {}
    if token_provider:
        token = await token_provider()
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
            if resp.status_code == 200:
                return resp.json().get("member", False)
            log.warning("Membership check returned %d for %s", resp.status_code, user_did)
            return False
    except httpx.HTTPError as exc:
        log.error("Membership check failed for %s: %s", user_did, exc)
        return False


def resolve_dataset_owner(
    governance_yaml_path: str,
    dataset_id: str,
    overlay_name: str | None = None,
) -> str | None:
    """Resolve the first ownership alias for a dataset from governance config."""
    path = Path(governance_yaml_path)
    resolver = GovernanceResolver.from_file_with_override(path, overlay_name=overlay_name)
    rule = resolver.resolve(dataset_id)
    if rule.ownership:
        return rule.ownership[0].name
    return None
