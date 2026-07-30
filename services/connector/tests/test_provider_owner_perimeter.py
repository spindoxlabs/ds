"""A provider write is confined to the owners the caller represents.

`connector.provider.write` says *what* a caller may do. It never said *whose* data
they may do it to — so an operator for one participant could delete another
participant's asset through the API. The portal filtered its buttons by owner,
which made the gap invisible: the UI looked scoped and the endpoint was not.

The role bundle `ds-participant-admin` is documented as scoped to one participant.
These tests are what make that true rather than aspirational.

Note the membership source. It is the Keycloak `organization` claim — the
*operator → owner* relation — and deliberately **not** the identity registry's
`OrganizationMembership`, which is the consent subject-pool keyed by a data
subject's DID. A provider operator legitimately has no DID at all, so sourcing
this from the registry would refuse every operator in the deployment.
"""
from __future__ import annotations

import jwt as pyjwt
import pytest


def _user_headers(*groups: str, organizations: dict | None = None) -> dict:
    """A *user* bearer: authority from groups, not from a scope claim."""
    claims: dict = {
        "sub": "operator-1",
        "email": "operator@example.test",
        "preferred_username": "operator@example.test",
        "groups": list(groups),
    }
    if organizations:
        claims["organization"] = organizations
    token = pyjwt.encode(claims, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# The property key a real EDC returns. Written by
# `connector/services/governance.py` as `f"{prefix}:owner"`, where the prefix comes
# from the active ODRL profile.
#
# The first cut of these tests invented `ds:owner` and passed, while the guard
# enforced **nothing** against a real EDC — an unrecognised key reads as "no owner",
# which is an allow. `--flow user-authority` caught it; the fixture now uses the real
# key, and `test_owner_is_read_by_local_name` pins the prefix-independence so the
# same mistake cannot recur from a profile change.
OWNER_PROPERTY = "dsp-policy:owner"


class _FakeEdc:
    """Minimal stand-in: the perimeter only reads the asset's owner property."""

    def __init__(self, owner: str | None, *, key: str = OWNER_PROPERTY):
        self._owner = owner
        self._key = key
        self.deleted: list[str] = []

    async def get_asset(self, asset_id: str):
        properties: dict[str, str] = {}
        if self._owner is not None:
            properties[self._key] = self._owner
            # A sibling whose local name is *not* `owner`, so a sloppy match cannot
            # pick it up instead.
            properties["dsp-policy:ownerDid"] = "did:web:someone.example.test"
        return {"@id": asset_id, "properties": properties}

    async def delete_asset(self, asset_id: str):
        self.deleted.append(asset_id)


@pytest.fixture
def owned_by(client):
    """Point the app's provider EDC at an asset with a chosen owner."""

    def _install(owner: str | None, *, key: str = OWNER_PROPERTY) -> _FakeEdc:
        edc = _FakeEdc(owner, key=key)
        client._transport.app.state.provider_edc = edc
        return edc

    return _install


ASSET = "datasets.silver.meters_15m"


@pytest.mark.asyncio
async def test_operator_of_the_owning_org_may_delete(client, owned_by):
    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            "ds-participant-admin",
            organizations={"example-org": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 204
    assert edc.deleted == [ASSET]


@pytest.mark.asyncio
async def test_operator_of_another_org_is_refused(client, owned_by):
    """The whole point: a valid `connector.provider.write` holder, refused because
    the asset is not theirs."""
    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            "ds-participant-admin",
            organizations={"grid-operator": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 403
    assert edc.deleted == []


@pytest.mark.asyncio
async def test_holder_with_no_organisations_is_allowed_by_default(client, owned_by):
    """A deployment that models no organisations is not one where every operator
    has lost their rights.

    This is a deliberate reversal of the first cut, which refused. Refusing here
    breaks every single-owner deployment that never declared a Keycloak
    organisation, and the way operators "fix" that is by granting
    ``connector.admin`` — which crosses **every** owner and is strictly worse than
    the thing being prevented. So the default allows and says so in the log, and
    deployments that do model owners tighten it with the flag below.
    """
    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers("ds-participant-admin"),
    )
    assert r.status_code == 204
    assert edc.deleted == [ASSET]


@pytest.mark.asyncio
async def test_strict_mode_refuses_a_holder_with_no_organisations(
    client, owned_by, monkeypatch
):
    """Where organisations *are* modelled, a missing claim means the caller was
    never scoped — not that scoping is off."""
    from connector import dependencies
    from connector.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(
        dependencies, "get_settings", lambda: settings.model_copy(
            update={"owner_scoping_strict": True}
        )
    )

    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers("ds-participant-admin"),
    )
    assert r.status_code == 403
    assert edc.deleted == []


# ── Authority, not membership (the fail-open case) ───────────────────────────


@pytest.mark.asyncio
async def test_viewer_in_the_owning_org_is_refused(client, owned_by):
    """The defect this closes.

    A read-only auditor for the owning organisation who administers a *different*
    one used to pass: the check asked "is a member **and** holds write somewhere",
    and flattened authority answered yes. It now asks whether the write is held
    **within** this owner.
    """
    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            organizations={
                "example-org": {"groups": ["ds-participant-viewer"]},
                "grid-operator": {"groups": ["ds-participant-admin"]},
            },
        ),
    )
    assert r.status_code == 403
    assert edc.deleted == []


@pytest.mark.asyncio
async def test_admin_in_the_owning_org_passes_while_holding_other_seats(
    client, owned_by
):
    """The mirror image, so the test above is not passing for the wrong reason."""
    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            organizations={
                "example-org": {"groups": ["ds-participant-admin"]},
                "grid-operator": {"groups": ["ds-participant-viewer"]},
            },
        ),
    )
    assert r.status_code == 204
    assert edc.deleted == [ASSET]


@pytest.mark.asyncio
async def test_realm_level_grant_is_deployment_wide(client, owned_by):
    """A realm-level bundle is not organisation-scoped. A single-participant
    deployment grants at realm level and must keep working."""
    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            "ds-participant-admin",
            organizations={"example-org": {"groups": []}},
        ),
    )
    assert r.status_code == 204
    assert edc.deleted == [ASSET]


# ── Owner aliases resolve through the registry ───────────────────────────────


class _FakeOwners:
    """`example` and `example-org` are the same owner — `Owner.aliases[]`."""

    def __init__(self):
        self.calls: list[str] = []

    async def by_id(self, alias: str):
        self.calls.append(alias)
        if alias in {"example", "example-org"}:
            return type("Entry", (), {"id": "example-org"})()
        return None


@pytest.mark.asyncio
async def test_an_alias_of_the_owner_is_the_owner(client, owned_by):
    """A governance file using the short alias and a realm using the long one
    describe the same organisation. String comparison said otherwise and refused —
    fail-closed, but wrong, and invisible until an operator was locked out."""
    edc = owned_by("example")
    registry = _FakeOwners()
    client._transport.app.state.owners_registry = registry

    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            organizations={"example-org": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 204
    assert edc.deleted == [ASSET]
    assert "example" in registry.calls and "example-org" in registry.calls


@pytest.mark.asyncio
async def test_an_unrelated_owner_is_still_refused_after_resolution(client, owned_by):
    """Resolution must not become a way to match anything: an alias the registry
    does not know falls back to its literal name rather than to a wildcard."""
    edc = owned_by("example-org")
    client._transport.app.state.owners_registry = _FakeOwners()

    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            organizations={"grid-operator": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 403
    assert edc.deleted == []


@pytest.mark.asyncio
async def test_unowned_asset_is_not_confined(client, owned_by):
    """Ownership is optional in governance.yaml. An unowned asset belongs to the
    participant as a whole, so refusing here would break every deployment that
    declares none — and it matches the portal's own `canManageAsset`."""
    edc = owned_by(None)
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers("ds-participant-admin"),
    )
    assert r.status_code == 204
    assert edc.deleted == [ASSET]


@pytest.mark.asyncio
async def test_operator_grant_is_not_owner_scoped(client, owned_by):
    """`connector.admin` is the deployment operator's grant, not a participant's.
    It crosses owners by design — that is what distinguishes it from
    `ds-participant-admin`."""
    edc = owned_by("someone-elses-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers("ds-admin"),
    )
    assert r.status_code == 204
    assert edc.deleted == [ASSET]


@pytest.mark.asyncio
async def test_service_token_is_unaffected(client, owned_by):
    """Service clients hold `connector.provider.write` to run syncs and have no
    organisations to be a member of. Confining them would break the dev/CI
    identity and every automated publish."""
    from tests import make_headers

    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}", headers=make_headers(scope="connector.admin")
    )
    assert r.status_code == 204
    assert edc.deleted == [ASSET]


# ── The owner property is read by local name, not by a guessed prefix ─────────


@pytest.mark.parametrize(
    "key",
    [
        "dsp-policy:owner",                        # today's profile prefix
        "custom:owner",                            # a deployment that renamed it
        "https://w3id.org/dsp/policy/owner",       # expanded, not compacted
        "owner",                                   # bare
    ],
)
@pytest.mark.asyncio
async def test_owner_is_read_by_local_name(client, owned_by, key):
    """Whatever the prefix, the owner is found — so scoping cannot be turned off by
    a profile change or by EDC compacting differently."""
    edc = owned_by("example-org", key=key)
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            organizations={"grid-operator": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 403, f"owner not recognised from key {key!r}"
    assert edc.deleted == []
