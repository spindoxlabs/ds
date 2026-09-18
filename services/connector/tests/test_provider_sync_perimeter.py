"""Who may publish at this connector, and what the sync answers when it fails.

Two items of `a-participant-publishes-and-the-sync-reconciles`, together in one
file because they are the two halves of one call: who is allowed to make it, and
whether its answer can be believed.

**The perimeter (items 5 + 6).** `connector.provider.write` said *what* a caller
may do and never *whose connector*. `POST /provider/sync` acts on the participant
as a whole, so it had no owner to scope against and carried no perimeter at all —
and `ds-participant-admin` is a realm group, which is not bound to any connector.
In a realm serving several participants, one participant's operator could publish
at every other participant's connector. Granting the organisation clients the
same permission (item 5, self-service publishing) would have widened that to
every organisation in the realm, which is why the two land together.

**The status code (item 3).** The route answered `200` whatever happened. A live
deployment's every dataset failed at `delete_asset` with an empty-bodied 400, the
route answered 200, and the publishing step — which checked the status code —
reported success against two empty catalogues.
"""

from __future__ import annotations

import jwt as pyjwt
import pytest
from ds_auth import ORGANISATION_CLIENT_SCOPES

from tests import _claims, make_headers, make_org_headers

#: What identity-registry provisions an organisation client with — the realm
#: grant, read from the one list that defines it rather than restated here, so a
#: change to `CONNECTOR_SERVICE_SCOPES` cannot leave this suite asserting against
#: a grant no organisation actually holds.
ORG_SCOPES = tuple(ORGANISATION_CLIENT_SCOPES)


def _org_headers(context: str | None = None) -> dict:
    return make_org_headers(context=context, scopes=ORG_SCOPES)


def _user_headers(*groups: str, organizations: dict | None = None) -> dict:
    claims: dict = _claims(
        sub="operator-1",
        email="operator@example.test",
        preferred_username="operator@example.test",
        groups=list(groups),
    )
    if organizations:
        claims["organization"] = organizations
    return {
        "Authorization": f"Bearer {pyjwt.encode(claims, 'secret', algorithm='HS256')}"
    }


class _OwnersRegistry:
    """Resolves an owner alias to its participant DID, as the registry does."""

    def __init__(self, mapping: dict[str, str]):
        self._mapping = mapping

    async def by_id(self, alias: str):
        did = self._mapping.get(alias)
        if did is None:
            return None
        return type("Owner", (), {"id": alias, "did": did})()

    async def canonical_uri(self, alias: str):
        return self._mapping.get(alias)


@pytest.fixture(autouse=True)
def _wired(client):
    """The provider EDC and the provenance bridge the lifespan would build.

    `attach_edc` gives the test app `state.edc`; the sync route reads
    `state.provider_edc` and `state.prov`.
    """
    from .fake_edc import FakeEdc, NullProv

    app = client._transport.app
    edc = FakeEdc()
    app.state.provider_edc = edc
    app.state.prov = NullProv()
    return edc


@pytest.fixture
def owners(client):
    def _install(mapping: dict[str, str]):
        registry = _OwnersRegistry(mapping)
        client._transport.app.state.owners_registry = registry
        return registry

    return _install


@pytest.fixture
def no_edc(client, monkeypatch):
    """Publish against nothing: the perimeter answers before the sync is reached.

    These tests are about *who is admitted*, so what the sync would then do to an
    EDC is deliberately not part of them — a 403 and a 502 are different answers
    and the test has to be able to tell them apart.
    """

    async def _fail(*_args, **_kwargs):
        raise AssertionError("the sync ran; the perimeter should have refused first")

    monkeypatch.setattr(
        "connector.services.provider_service.load_exposed_datasets", _fail
    )


# ── The organisation publishes its own catalogue ─────────────────────────────


@pytest.mark.asyncio
async def test_this_participant_s_organisation_may_publish(client, monkeypatch):
    """Item 5, approved: a registered participant publishes its own datasets."""
    monkeypatch.setattr(
        "connector.services.provider_service.load_exposed_datasets",
        lambda *_a, **_k: {},
    )
    r = await client.post("/provider/sync", headers=_org_headers())
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_another_participant_s_organisation_is_refused(client, no_edc):
    """Item 6, the defect: a holder could sync any connector it could reach.

    The token is valid, carries `connector.provider.write` and names a real
    participant — just not this one. Without the perimeter this is a 200 that
    republishes someone else's catalogue.
    """
    r = await client.post(
        "/provider/sync",
        headers=_org_headers(context="did:web:other.dataspaces.localhost"),
    )
    assert r.status_code == 403
    assert "its own participant" in r.json()["detail"]


# ── A person is bounded by the organisation they act for ─────────────────────


@pytest.mark.asyncio
async def test_an_operator_of_this_participant_may_publish(client, owners, monkeypatch):
    from connector.config import get_settings

    owners({"example-org": get_settings().participant_did})
    monkeypatch.setattr(
        "connector.services.provider_service.load_exposed_datasets",
        lambda *_a, **_k: {},
    )
    r = await client.post(
        "/provider/sync",
        headers=_user_headers(
            "ds-participant-admin",
            organizations={"example-org": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_an_operator_of_another_participant_is_refused(client, owners, no_edc):
    """`ds-participant-admin` is a realm group; this is what binds it to a connector."""
    owners(
        {
            "example-org": "did:web:rec.dataspaces.localhost",
            "grid-operator": "did:web:grid-operator.dataspaces.localhost",
        }
    )
    r = await client.post(
        "/provider/sync",
        headers=_user_headers(
            "ds-participant-admin",
            organizations={"grid-operator": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_a_viewer_of_this_participant_is_refused(client, owners, no_edc):
    """Authority within the organisation, not membership of it.

    The same fail-open `_own_owner_only` closes: a read-only seat in the right
    organisation is not a publisher. Here it is refused by the permission check
    before the perimeter, which is the correct order and worth pinning — a
    perimeter that had to catch this would mean the permission table was wrong.
    """
    from connector.config import get_settings

    owners({"example-org": get_settings().participant_did})
    r = await client.post(
        "/provider/sync",
        headers=_user_headers(
            "ds-participant-viewer",
            organizations={"example-org": {"groups": ["ds-participant-viewer"]}},
        ),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_a_deployment_that_models_no_organisations_still_publishes(
    client, monkeypatch
):
    """The same exemption `_own_owner_only` makes, and for the same reason.

    Refusing here breaks every single-owner deployment that never declared a
    Keycloak organisation, and the way operators "fix" that is by granting
    `connector.admin` — which crosses every participant and is strictly worse.
    """
    monkeypatch.setattr(
        "connector.services.provider_service.load_exposed_datasets",
        lambda *_a, **_k: {},
    )
    r = await client.post(
        "/provider/sync", headers=_user_headers("ds-participant-admin")
    )
    assert r.status_code == 200


# ── The two unbound classes, stated rather than assumed ──────────────────────


@pytest.mark.asyncio
async def test_the_deployment_operator_crosses_participants(client, monkeypatch):
    """`connector.admin` is the deployment's grant, not a participant's.

    That is exactly what distinguishes it from `ds-participant-admin`, and the
    distinction only means something if it is asserted.
    """
    monkeypatch.setattr(
        "connector.services.provider_service.load_exposed_datasets",
        lambda *_a, **_k: {},
    )
    r = await client.post("/provider/sync", headers=make_headers("connector.admin"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_the_publisher_client_publishes(client, monkeypatch):
    """`svc-ds-publisher`: a plain service holding exactly the two provider grants.

    It names no participant, so there is nothing to bind it to — it is a
    deployment-level actor like `connector.admin`, and the control is that it
    holds nothing else (no `management-api:*`, no admin). Asserted here so the
    one class this perimeter does not narrow is visible in the tests rather than
    only in a comment.
    """
    monkeypatch.setattr(
        "connector.services.provider_service.load_exposed_datasets",
        lambda *_a, **_k: {},
    )
    r = await client.post(
        "/provider/sync",
        headers=make_headers("connector.provider.read connector.provider.write"),
    )
    assert r.status_code == 200


# ── The answer agrees with the body (item 3) ─────────────────────────────────


@pytest.mark.asyncio
async def test_a_sync_that_published_nothing_is_not_a_success(client, monkeypatch):
    """The measured defect: every dataset in `errors`, and a `200`.

    Run against the route as it was, this test fails on `r.status_code == 200`,
    which is the whole point of writing it.
    """

    def _boom(*_args, **_kwargs):
        raise RuntimeError("governance is unreadable")

    monkeypatch.setattr(
        "connector.services.provider_service.load_exposed_datasets", _boom
    )
    r = await client.post("/provider/sync", headers=make_headers("connector.admin"))
    assert r.status_code == 502
    body = r.json()
    assert body["errors"]
    assert body["synced"] == []


@pytest.mark.asyncio
async def test_a_partial_publish_is_207_and_keeps_both_lists(client, monkeypatch):
    """A partial publish is a real state, and the list of what landed survives it.

    Collapsing it into a bare failure would throw away what an operator fixes
    forward from.
    """
    from ds.governance.models import DataspaceSpec, GovernanceRuleV2

    def _rule(purposes):
        return GovernanceRuleV2(
            access_level="open",
            classification="green",
            dataspace=DataspaceSpec(expose=True, purpose=purposes),
        )

    monkeypatch.setattr(
        "connector.services.provider_service.load_exposed_datasets",
        lambda *_a, **_k: {
            "datasets.gold.good": _rule(["GridMonitoring"]),
            "datasets.gold.bad": _rule(["not-a-purpose"]),
        },
    )
    r = await client.post("/provider/sync", headers=make_headers("connector.admin"))
    assert r.status_code == 207
    body = r.json()
    assert body["synced"] == ["datasets.gold.good"]
    assert len(body["errors"]) == 1


@pytest.mark.asyncio
async def test_a_clean_sync_is_still_200(client, monkeypatch):
    monkeypatch.setattr(
        "connector.services.provider_service.load_exposed_datasets",
        lambda *_a, **_k: {},
    )
    r = await client.post("/provider/sync", headers=make_headers("connector.admin"))
    assert r.status_code == 200
    assert r.json() == {"synced": [], "withdrawn": [], "skipped": [], "errors": []}
