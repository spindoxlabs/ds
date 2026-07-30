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


class _FakeEdc:
    """Minimal stand-in: the perimeter only reads the asset's `ds:owner`."""

    def __init__(self, owner: str | None):
        self._owner = owner
        self.deleted: list[str] = []

    async def get_asset(self, asset_id: str):
        properties: dict[str, str] = {}
        if self._owner is not None:
            properties["ds:owner"] = self._owner
        return {"@id": asset_id, "properties": properties}

    async def delete_asset(self, asset_id: str):
        self.deleted.append(asset_id)


@pytest.fixture
def owned_by(client):
    """Point the app's provider EDC at an asset with a chosen owner."""

    def _install(owner: str | None) -> _FakeEdc:
        edc = _FakeEdc(owner)
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
async def test_holder_with_no_organisations_is_refused(client, owned_by):
    """A realm that never modelled organisations must not thereby grant everyone
    everything — the absence of a claim is not authority."""
    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers("ds-participant-admin"),
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
