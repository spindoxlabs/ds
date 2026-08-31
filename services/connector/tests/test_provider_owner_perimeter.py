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

import httpx
import jwt as pyjwt
import pytest

from tests import _claims


def _user_headers(*groups: str, organizations: dict | None = None) -> dict:
    """A *user* bearer: authority from groups, not from a scope claim."""
    claims: dict = _claims(
        sub="operator-1",
        email="operator@example.test",
        preferred_username="operator@example.test",
        groups=list(groups),
    )
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

    async def delete_policy(self, policy_id: str):
        self.deleted.append(policy_id)

    async def delete_contract_definition(self, contract_id: str):
        self.deleted.append(contract_id)


@pytest.fixture
def owned_by(client):
    """Point the app's provider EDC at an asset with a chosen owner."""

    def _install(owner: str | None, *, key: str = OWNER_PROPERTY) -> _FakeEdc:
        edc = _FakeEdc(owner, key=key)
        client._transport.app.state.provider_edc = edc
        return edc

    return _install


ASSET = "datasets.silver.meters_15m"


@pytest.mark.rule("C-16")
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


@pytest.mark.rule("C-16", "C-17")
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


@pytest.mark.rule("C-16")
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
        dependencies,
        "get_settings",
        lambda: settings.model_copy(update={"owner_scoping_strict": True}),
    )

    edc = owned_by("example-org")
    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers("ds-participant-admin"),
    )
    assert r.status_code == 403
    assert edc.deleted == []


# ── Authority, not membership (the fail-open case) ───────────────────────────


@pytest.mark.rule("C-16", "C-17")
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


@pytest.mark.rule("C-16")
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
        "dsp-policy:owner",  # today's profile prefix
        "custom:owner",  # a deployment that renamed it
        "https://w3id.org/dsp/policy/owner",  # expanded, not compacted
        "owner",  # bare
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


# ── Layer B: a foreign realm's organisation names ────────────────────────────
#
# In a realm ds did not name, the claim's organisation aliases match no `Owner.id`
# and every comparison fails — the perimeter refuses every operator. Fail-closed,
# but a lock-out, and the reason posture B needs this map before per-owner scoping
# is deployable at all.


@pytest.fixture
def owner_aliases(monkeypatch):
    """Configure CONNECTOR_OWNER_ALIASES for one test."""

    def _set(raw: str):
        from connector import dependencies
        from connector.config import get_settings

        dependencies._owner_aliases.cache_clear()
        settings = get_settings().model_copy(update={"owner_aliases": raw})
        monkeypatch.setattr(dependencies, "get_settings", lambda: settings)

    yield _set
    from connector import dependencies

    dependencies._owner_aliases.cache_clear()


@pytest.mark.asyncio
async def test_a_foreign_organisation_name_maps_onto_a_ds_owner(
    client, owned_by, owner_aliases
):
    """The realm calls it `CELINE-REC-01`; ds calls it `example-org`."""
    owner_aliases('{"CELINE-REC-01": "example-org"}')
    edc = owned_by("example-org")

    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            organizations={"CELINE-REC-01": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 204
    assert edc.deleted == [ASSET]


@pytest.mark.rule("C-16")
@pytest.mark.asyncio
async def test_an_unmapped_foreign_organisation_is_still_refused(
    client, owned_by, owner_aliases
):
    """The map translates; it does not wave through. A foreign name with no entry
    keeps its literal value and matches nothing."""
    owner_aliases('{"CELINE-REC-01": "example-org"}')
    edc = owned_by("example-org")

    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            organizations={"CELINE-REC-99": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 403
    assert edc.deleted == []


@pytest.mark.rule("C-16")
@pytest.mark.asyncio
async def test_a_malformed_owner_map_does_not_open_the_perimeter(
    client, owned_by, owner_aliases
):
    """A typo yields an empty map — no translation — never a wildcard."""
    owner_aliases("{not json")
    edc = owned_by("example-org")

    r = await client.delete(
        f"/provider/assets/{ASSET}",
        headers=_user_headers(
            organizations={"CELINE-REC-01": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 403
    assert edc.deleted == []


# ── Policies and contracts: owner resolved through governance ────────────────
#
# EDC labels an **asset** with its owner and labels a policy or contract
# definition with nothing at all. They are not anonymous, though: their ids are
# derived from the dataset key, so governance is the one place that knows which
# owner they belong to. Asking EDC cannot work — a contract definition references
# assets only through a selector and a policy definition references nothing.
#
# Left unscoped, an operator for one participant could delete the *policy* under
# which another participant's data is offered. The asset survives; the terms it is
# offered on do not.


@pytest.fixture
def governed(monkeypatch, owned_by):
    """Stub the governance→owner index the perimeter consults."""

    def _install(index: dict[str, str]):
        from connector import dependencies

        # The route still resolves its own EDC dependency; only the *owner* lookup
        # goes through governance for these object kinds.
        owned_by(None)
        monkeypatch.setattr(
            "connector.services.governance.owner_by_edc_id", lambda *a, **k: index
        )
        return dependencies

    return _install


POLICY = "datasets-silver-meters_15m-policy"
CONTRACT = "datasets-silver-meters_15m-contract"


@pytest.mark.rule("C-16")
@pytest.mark.asyncio
async def test_policy_delete_is_owner_scoped(client, governed):
    governed({POLICY: "example-org"})
    r = await client.delete(
        f"/provider/policies/{POLICY}",
        headers=_user_headers(
            organizations={"grid-operator": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 403


@pytest.mark.rule("C-16")
@pytest.mark.asyncio
async def test_contract_delete_is_owner_scoped(client, governed):
    governed({CONTRACT: "example-org"})
    r = await client.delete(
        f"/provider/contracts/{CONTRACT}",
        headers=_user_headers(
            organizations={"grid-operator": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_the_owning_operator_may_delete_a_policy(client, governed):
    """So the refusals above are not passing for want of any authority."""
    governed({POLICY: "example-org"})
    r = await client.delete(
        f"/provider/policies/{POLICY}",
        headers=_user_headers(
            organizations={"example-org": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code != 403


@pytest.mark.asyncio
async def test_an_id_governance_does_not_know_is_not_confined(client, governed):
    """ "Unknown id" is the endpoint's 404 to report, not an authorization
    decision. Refusing here would turn "does not exist" into "not yours"."""
    governed({POLICY: "example-org"})
    r = await client.delete(
        "/provider/policies/some-other-policy",
        headers=_user_headers(
            organizations={"grid-operator": {"groups": ["ds-participant-admin"]}},
        ),
    )
    assert r.status_code != 403


def test_the_index_covers_policies_and_contracts_from_real_governance():
    """Against the shipped governance file, not a fabricated one — the M9 lesson:
    an index keyed on ids the test invented proves only that it agrees with itself.

    Every shipped file, discovered rather than named: this read
    `governance/governance.yaml`, which the participant rename replaced with one
    directory per participant. `owner_by_edc_id` returns `{}` for a path that
    does not exist, so the test failed on its own first assertion rather than on
    anything about ownership — and a single hardcoded path would have gone on
    ignoring the second provider's file after being repointed.
    """
    from pathlib import Path

    from connector.services.governance import owner_by_edc_id

    unit = Path(__file__).resolve().parents[1]
    files = sorted(unit.glob("governance-*/governance.yaml"))
    assert files, f"no governance-*/governance.yaml under {unit}"

    for path in files:
        index = owner_by_edc_id(str(path))
        assert index, f"no owned datasets resolved from {path.relative_to(unit)}"
        assert any(k.endswith("-policy") for k in index), path
        assert any(k.endswith("-contract") for k in index), path
        assert all(v for v in index.values()), (
            f"an unowned dataset leaked in as empty: {path}"
        )


# ── ENV-09 · a lookup that failed is not an absence of owner ─────────────────
#
# `_target_owner` used to return "" for *unowned*, *unknown id* **and** *the
# lookup blew up*, and the perimeter reads "" as "nothing to scope against" and
# allows. So with the provider EDC unreachable the guard was off: measured on a
# dev stack whose EDC was down, a grid-operator seat's delete of an example-org
# asset passed this perimeter and reached the handler.
#
# `test_unowned_asset_is_not_confined` and
# `test_an_id_governance_does_not_know_is_not_confined` above are the states
# that must keep allowing, and they are why this is a split rather than a
# blanket refusal: turning "does not exist" into "not yours" is a worse answer.


class _BrokenEdc:
    """A provider EDC that fails the owner lookup the way a real one does."""

    def __init__(self, error: Exception):
        self._error = error
        self.deleted: list[str] = []

    async def get_asset(self, asset_id: str):
        raise self._error

    async def delete_asset(self, asset_id: str):
        # Asserted on rather than the status alone: during a real outage the
        # handler fails too, so a 5xx cannot tell "refused" from "allowed and
        # then broke" — which is exactly how this stayed invisible.
        self.deleted.append(asset_id)


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"http://edc.invalid/v3/assets/{ASSET}")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"EDC get_asset {status}", request=request, response=response
    )


@pytest.fixture
def lookup_fails(client):
    def _install(error: Exception) -> _BrokenEdc:
        edc = _BrokenEdc(error)
        client._transport.app.state.provider_edc = edc
        return edc

    return _install


def _grid_operator() -> dict:
    return _user_headers(
        organizations={"grid-operator": {"groups": ["ds-participant-admin"]}},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, why",
    [
        (httpx.ConnectError("connection refused"), "the EDC is down"),
        (httpx.ReadTimeout("timed out"), "the EDC is slow"),
        (_http_error(500), "the EDC errored"),
        (_http_error(401), "the EDC rejected our management key"),
    ],
    ids=["unreachable", "timeout", "edc-500", "edc-401"],
)
@pytest.mark.rule("C-16", "C-17")
async def test_a_failed_owner_lookup_refuses_the_write(
    client, lookup_fails, error, why
):
    """Deny on error — the rule the root guide states for the constraint functions.

    The window is narrow and not empty, which is why this is a defect and not a
    theoretical one: `get_asset` can fail where the following `delete_asset`
    would have succeeded — one transient 5xx, a read timeout, a deserialisation
    error on a single asset — and then the delete goes through against another
    participant's data.
    """
    edc = lookup_fails(error)
    r = await client.delete(f"/provider/assets/{ASSET}", headers=_grid_operator())
    assert r.status_code == 403, why
    assert edc.deleted == [], "the write reached the handler despite the refusal"


@pytest.mark.rule("C-17")
@pytest.mark.asyncio
async def test_the_refusal_says_the_owner_could_not_be_determined(client, lookup_fails):
    """An unattributable 403 during an outage is an alarm that gets dismissed.

    `PermissionDenied` carries its message into the 403 body, so an operator can
    tell this from an ordinary cross-owner refusal — the two mean different
    things and want different fixes.
    """
    lookup_fails(httpx.ConnectError("connection refused"))
    r = await client.delete(f"/provider/assets/{ASSET}", headers=_grid_operator())
    assert "cannot determine which organisation owns" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_404_from_the_edc_is_an_answer_not_a_failure(client, lookup_fails):
    """ "There is no such asset" means there is no owner, so it is not confined.

    The one status that must stay on the allowing side: refusing here would turn
    the endpoint's own 404 into a 403, which tells a caller that someone else's
    asset exists.
    """
    lookup_fails(_http_error(404))
    r = await client.delete(f"/provider/assets/{ASSET}", headers=_grid_operator())
    assert r.status_code != 403


@pytest.mark.rule("C-17")
@pytest.mark.asyncio
async def test_an_unreadable_governance_file_refuses_a_policy_delete(
    client, monkeypatch, owned_by
):
    """Same split on the other lookup.

    The comment there already said that returning an empty index "would silently
    unscope every policy and contract in the deployment" — and then returned
    one. It now logs *and* refuses.
    """
    owned_by(None)

    def _boom(*args, **kwargs):
        raise FileNotFoundError("governance file not found: governance/governance.yaml")

    monkeypatch.setattr("connector.services.governance.owner_by_edc_id", _boom)
    r = await client.delete(f"/provider/policies/{POLICY}", headers=_grid_operator())
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_a_caller_with_no_organisations_is_unaffected_by_a_failed_lookup(
    client, lookup_fails
):
    """No security gain, so no availability cost.

    Owner scoping already allows this caller whatever the owner turns out to be
    (non-strict), so a failed lookup decides nothing for them. Refusing would
    take out every deployment that models no organisations the moment its EDC
    hiccups.
    """
    edc = lookup_fails(httpx.ConnectError("connection refused"))
    r = await client.delete(
        f"/provider/assets/{ASSET}", headers=_user_headers("ds-participant-admin")
    )
    assert r.status_code != 403
    assert edc.deleted == [ASSET]


@pytest.mark.asyncio
async def test_strict_mode_refuses_that_caller_too(client, lookup_fails, monkeypatch):
    """A deployment that models owners gets the tighter posture on both paths."""
    from connector.config import get_settings

    monkeypatch.setenv("CONNECTOR_OWNER_SCOPING_STRICT", "true")
    get_settings.cache_clear()
    try:
        edc = lookup_fails(httpx.ConnectError("connection refused"))
        r = await client.delete(
            f"/provider/assets/{ASSET}", headers=_user_headers("ds-participant-admin")
        )
    finally:
        get_settings.cache_clear()
    assert r.status_code == 403
    assert edc.deleted == []


@pytest.mark.asyncio
async def test_an_edc_outage_does_not_lock_out_the_operator_or_the_syncs(
    client, lookup_fails
):
    """What bounds the cost of denying, and it is deliberate ordering.

    `connector.admin` and every service principal return *before* the owner
    lookup happens — so an EDC outage cannot break the governance sync or stop
    the deployment operator from fixing it. A refusal that locked the operator
    out of the repair would be a worse failure than the one being prevented.
    """
    edc = lookup_fails(httpx.ConnectError("connection refused"))
    r = await client.delete(
        f"/provider/assets/{ASSET}", headers=_user_headers("ds-admin")
    )
    assert r.status_code != 403
    assert edc.deleted == [ASSET]
