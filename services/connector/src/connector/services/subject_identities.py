"""Subject DIDs → the usernames systems outside the dataspace key on.

A dataspace decision names people by DID. The systems that actually hold their
data do not: the REC registry resolves a member with
``Member.user_id == user.get_username()``. Something has to bridge the two, and
it must be the identity-registry, because that is where the link is stored —
deriving it anywhere else means guessing, and a wrong guess resolves to another
person's data.

Cached briefly. The mapping changes only when a person is (re)provisioned, while
the data-plane authorisation path asks for it on every cache miss, so a short TTL
removes a fan-out without letting a stale answer outlive a re-provisioning by
long.
"""

from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)

# Short by design: this is a hot path, and the mapping is stable.
_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, str]] = {}


async def resolve_usernames(
    dids: list[str],
    identity_registry_url: str,
    token_provider=None,
) -> dict[str, str]:
    """``{did: username}`` for every DID the registry can resolve.

    **Unresolvable DIDs are omitted, never guessed.** The caller uses the result
    to decide whose rows may leave, so an entry invented from an email local
    part or a DID path segment would be an authorisation decision made by string
    manipulation. Dropping a subject costs them access; inventing one costs
    somebody else their privacy.
    """
    if not dids or not identity_registry_url:
        return {}

    now = time.monotonic()
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for did in dids:
        entry = _cache.get(did)
        if entry and entry[0] > now:
            resolved[did] = entry[1]
        else:
            missing.append(did)

    if not missing:
        return resolved

    headers = {}
    if token_provider is not None:
        headers["Authorization"] = f"Bearer {await token_provider()}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{identity_registry_url.rstrip('/')}/users/identities",
                json={"dids": missing},
                headers=headers,
            )
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        # A registry that cannot answer means the subject set cannot be
        # translated. Returning what we have lets the caller deny on an empty
        # set, which is the right outcome — never a partial allow dressed up as
        # a complete one.
        log.warning("Subject identity resolution failed: %s", exc)
        return resolved

    expiry = time.monotonic() + _CACHE_TTL_SECONDS
    for item in response.json() or []:
        did, username = item.get("did"), item.get("username")
        if did and username:
            resolved[did] = username
            _cache[did] = (expiry, username)
    return resolved


def reset_cache() -> None:
    """Drop the cache — for tests, and for a re-provisioning that must be seen."""
    _cache.clear()
