"""T26 — `ir-cli org apply`: seed an organisation end to end.

The five lifecycle calls are each idempotent on their own; what these cover is
the *composition* — that walking them from one declarative entry reaches a
promoted participant, that a second run advances nothing and duplicates
nothing, and that a half-declared entry is refused before it leaves state
behind.

The tests drive `services.org_onboarding.apply_owner_entry` rather than the
typer command: the CLI is a thin renderer over it, and the API layer will want
the same function.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest import make_headers, register_enrolled
from sqlalchemy import func, select

from identity_registry.config import Settings
from identity_registry.db.models import (
    AgreementAcceptance,
    Credential,
    OrganizationApplication,
    Owner,
    Participant,
)
from identity_registry.services import org_onboarding as ops
from identity_registry.services.agreements import import_agreements
from identity_registry.services.crypto import encrypt_private_jwk, generate_key_pair

ALIAS = "example-community"
ORG_DID = "did:web:example-community.dataspaces.localhost"
AGREEMENT = "dataspace-participation"
ADMIN_HEADERS = make_headers()


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        oidc_issuer_url=None,
    )


def _entry(**dataspace_overrides) -> dict:
    """An owners.yaml entry carrying the ds-only `dataspace:` block."""
    block = {
        "legal_name": "Example Community Cooperative",
        "roles": ["consumer"],
        "dsp_address": "https://example-community/dsp",
        "registration_number": "IT12345678901",
        "registration_type": "vatID",
        "hq_country_code": "IT-TN",
        "legal_country_code": "IT-TN",
        "accepted": {"agreement": AGREEMENT, "version": "1.0", "locale": "en"},
        "verified_by": "ops@example.test",
        "evidence_ref": "TICKET-42",
    }
    block.update(dataspace_overrides)
    for key, value in list(block.items()):
        if value is None:
            del block[key]
    return {
        "id": ALIAS,
        "type": "schema:NGO",
        "name": "Example Community",
        "did": ORG_DID,
        "aliases": ["example-c"],
        "organization": {"create": True, "role": "rec"},
        "dataspace": block,
    }


async def _seed(db_session, tmp_path):
    """A bootstrapped trust anchor and an imported agreement — the two things
    the chain needs that an owners.yaml cannot carry."""
    settings = _settings(tmp_path)
    ta_did = f"did:web:{settings.trust_anchor_domain}"
    from identity_registry.db.models import Key

    kp = generate_key_pair(ta_did)
    db_session.add(
        Key(
            owner_did=ta_did,
            kid=kp.kid,
            private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
            public_jwk=kp.public_jwk,
        )
    )
    await import_agreements(
        db_session,
        [
            {
                "id": AGREEMENT,
                "version": "1.0",
                "effective_from": None,
                "applies_to": ["consumer", "provider"],
                "capacity": "processor",
                "texts": {"en": {"path": "x.md", "sha256": "deadbeef"}},
            }
        ],
    )
    await db_session.commit()
    return settings


# ── The chain ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_walks_the_operators_half_and_stops_at_enrolment(
    db_session, tmp_path
):
    """The chain an operator can complete **alone**, and where it now ends.

    It used to run all the way to a promoted participant, and the last two steps
    did that by minting the organisation's keypair and its STS secret here
    (`D-51`). An operator cannot do those on the organisation's behalf any more,
    so the seed does everything that is genuinely a governance judgement —
    application, verification, agreement — and reports the rest as *awaiting
    enrolment* rather than failing.

    Reported rather than failed on purpose: a seed of ten organisations, none of
    which has stood up a registry yet, is the **normal** state of a fresh
    deployment, not ten errors.
    """
    settings = await _seed(db_session, tmp_path)

    outcome = await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()

    assert outcome.ok, outcome.error
    assert outcome.applied and outcome.changed
    actions = {s.step: s.action for s in outcome.steps}
    assert actions == {
        "application": "created",
        "verification": "created",
        "agreement": "accepted",
        "credential": "skipped",
        "participant": "skipped",
    }
    assert all(
        s.detail == "awaiting enrolment" for s in outcome.steps if s.action == "skipped"
    )

    owner = (
        await db_session.execute(select(Owner).where(Owner.id == ALIAS))
    ).scalar_one()
    assert owner.status == "verified"
    assert owner.verified_by == "ops@example.test"
    assert owner.evidence_ref == "TICKET-42"
    assert owner.agreement_capacity == "processor"
    # The entry's own presentation and lookup keys survive the promotion —
    # governance `ownership[].name` resolves by alias.
    assert owner.type == "schema:NGO"
    assert owner.aliases == ["example-c"]
    assert owner.organization_config == {"create": True, "role": "rec"}

    # No participant, and no credential: both wait on a key the organisation
    # has not yet proved control of.
    assert (
        await db_session.execute(select(Participant).where(Participant.did == ORG_DID))
    ).scalar_one_or_none() is None
    assert (await db_session.execute(select(Credential))).scalars().first() is None


@pytest.mark.asyncio
async def test_apply_completes_once_the_organisation_has_enrolled(db_session, tmp_path):
    """The other half of the handshake, and the chain closes.

    Enrolment registers the DID with the **public** key the organisation
    generated. Issuance needs nothing more — the credential is signed with the
    anchor's key and merely names the subject — so `org apply` run again now
    issues and promotes.
    """
    settings = await _seed(db_session, tmp_path)
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()

    await register_enrolled(db_session, ORG_DID, roles=["consumer"])

    outcome = await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()

    actions = {s.step: s.action for s in outcome.steps}
    assert actions["credential"] == "issued"
    # `unchanged`, not `promoted`: **enrolment already registered the
    # participant**. Promotion is now the gate (an active OrganizationCredential
    # must exist) plus a refresh of roles and scopes, not the act that brings a
    # participant into being.
    assert actions["participant"] == "unchanged"

    participant = (
        await db_session.execute(select(Participant).where(Participant.did == ORG_DID))
    ).scalar_one()
    assert participant.active is True
    assert participant.roles == ["consumer"]
    # **No STS secret.** How a participant authenticates to its own STS is not
    # the anchor's to decide (`D-51`).
    assert participant.sts_client_secret is None


@pytest.mark.asyncio
async def test_apply_is_idempotent(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)

    first = await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()
    owner = (
        await db_session.execute(select(Owner).where(Owner.id == ALIAS))
    ).scalar_one()
    verified_at, accepted_at = owner.verified_at, owner.agreement_accepted_at

    second = await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()

    assert first.ok and second.ok
    assert second.changed is False
    # `skipped` is not a change: the two steps waiting on enrolment stay waiting.
    assert {s.action for s in second.steps} <= {"unchanged", "skipped"}

    # Nothing duplicated. Only the acceptance exists: the credential and the
    # participant wait on enrolment, so "one of each" is no longer the shape a
    # second run must not double — "none of the two, one of the third" is.
    for model, expected in (
        (Credential, 0),
        (AgreementAcceptance, 1),
        (Participant, 0),
    ):
        count = (
            await db_session.execute(select(func.count()).select_from(model))
        ).scalar_one()
        assert count == expected, model.__name__

    # And nothing re-stamped: `verified_at` records when the check happened, not
    # when the seed last ran. A helm bootstrap re-runs on every pod start.
    await db_session.refresh(owner)
    assert owner.verified_at == verified_at
    assert owner.agreement_accepted_at == accepted_at


# ── Refusals ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entry_without_dataspace_block_is_skipped(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)
    entry = {"id": "other-consumer", "name": "Someone Else"}

    outcome = await ops.apply_owner_entry(db_session, settings, entry)

    assert outcome.ok
    assert outcome.applied is False
    assert (await db_session.execute(select(Owner))).scalars().first() is None


@pytest.mark.asyncio
async def test_verified_by_is_required(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)

    outcome = await ops.apply_owner_entry(
        db_session, settings, _entry(verified_by=None)
    )
    await db_session.rollback()

    assert not outcome.ok
    assert "verified_by" in outcome.error
    assert (await db_session.execute(select(Owner))).scalars().first() is None


@pytest.mark.rule("P-1")
@pytest.mark.asyncio
async def test_promotion_without_an_agreement_is_refused_before_any_write(
    db_session, tmp_path
):
    settings = await _seed(db_session, tmp_path)

    outcome = await ops.apply_owner_entry(db_session, settings, _entry(accepted=None))
    await db_session.rollback()

    assert not outcome.ok
    assert "accepted" in outcome.error
    # Refused up front, so no half-onboarded owner is left behind.
    assert (await db_session.execute(select(Owner))).scalars().first() is None


@pytest.mark.asyncio
async def test_unimported_agreement_names_itself(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)
    entry = _entry(accepted={"agreement": AGREEMENT, "version": "9.9"})

    outcome = await ops.apply_owner_entry(db_session, settings, entry)
    await db_session.rollback()

    assert not outcome.ok
    assert f"{AGREEMENT}@9.9" in outcome.error


@pytest.mark.asyncio
async def test_entry_without_dsp_address_stops_at_the_credential(db_session, tmp_path):
    settings = await _seed(db_session, tmp_path)

    outcome = await ops.apply_owner_entry(
        db_session, settings, _entry(dsp_address=None)
    )
    await db_session.commit()

    assert outcome.ok, outcome.error
    actions = {s.step: s.action for s in outcome.steps}
    await register_enrolled(db_session, ORG_DID, roles=["consumer"])
    outcome = await ops.apply_owner_entry(
        db_session, settings, _entry(dsp_address=None)
    )
    await db_session.commit()
    actions = {s.step: s.action for s in outcome.steps}
    assert actions["credential"] == "issued"
    # Still skipped: the entry declares no DSP address, so there is nothing to
    # promote *against*. The participant row exists because enrolment created
    # it, which is a different fact from this entry being promotable.
    assert actions["participant"] == "skipped"
    assert "no dataspace.dsp_address" in next(
        s.detail for s in outcome.steps if s.step == "participant"
    )


# ── Equivalence with the API path ─────────────────────────────────


@pytest.mark.asyncio
async def test_applied_state_matches_the_api_driven_chain(client, db_session, tmp_path):
    """`org apply` and the admin API must leave the same rows.

    `ds-e2e`'s `org-onboarding` flow walks the HTTP chain, and an operator
    seeding a deployment walks this one. If the two diverge, whichever path a
    given environment happened to use decides what its owners look like — so
    the claim is checked rather than argued from shared call sites.
    """
    settings = await _seed(db_session, tmp_path)
    await register_enrolled(db_session, ORG_DID, roles=["consumer"])
    headers = ADMIN_HEADERS

    api_alias, api_did = "api-org", "did:web:api-org.dataspaces.localhost"
    dsp = "https://org/dsp"
    common = {
        "legal_name": "Example Community Cooperative",
        "registration_number": "IT12345678901",
        "registration_type": "vatID",
        "hq_country_code": "IT-TN",
        "legal_country_code": "IT-TN",
        "roles": ["consumer"],
        "dsp_address": dsp,
    }

    app = await client.post(
        "/admin/organizations/applications",
        json={"alias": api_alias, "did": api_did, **common},
        headers=headers,
    )
    assert app.status_code == 201, app.text
    r = await client.patch(
        f"/admin/organizations/applications/{app.json()['id']}",
        json={"status": "verified", "verified_by": "ops@example.test"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/admin/owners/{api_alias}/agreement",
        json={"agreement_id": AGREEMENT, "version": "1.0", "locale": "en"},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text
    # Both paths now cross the same seam: an organisation is issued to only once
    # it has enrolled. Seeding it here is what keeps this an equivalence test
    # rather than a test that one path skips a gate the other enforces.
    await register_enrolled(db_session, api_did, roles=["consumer"])
    r = await client.post(
        "/admin/credentials/organization",
        json={"alias": api_alias, "roles": ["consumer"], "dsp_address": dsp},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"/admin/owners/{api_alias}/promote",
        json={"dsp_address": dsp, "roles": ["consumer"]},
        headers=headers,
    )
    assert r.status_code in (200, 201), r.text

    cli_entry = _entry(dsp_address=dsp)
    outcome = await ops.apply_owner_entry(db_session, settings, cli_entry)
    await db_session.commit()
    assert outcome.ok, outcome.error

    compared = (
        "type",
        "name",
        "status",
        "verified_by",
        "registration_number",
        "registration_type",
        "hq_country_code",
        "legal_country_code",
        "agreement_id",
        "agreement_version",
        "agreement_capacity",
    )
    owners = {
        oid: (
            await db_session.execute(select(Owner).where(Owner.id == oid))
        ).scalar_one()
        for oid in (api_alias, ALIAS)
    }
    # `type` is the one field the API chain cannot carry — an application has no
    # schema.org type — so the entry supplies it and the API path keeps the
    # default. Everything else must agree.
    assert owners[ALIAS].type == "schema:NGO"
    assert owners[api_alias].type == "schema:Organization"
    for f in compared:
        if f == "type":
            continue
        assert getattr(owners[api_alias], f) == getattr(owners[ALIAS], f), f

    parts = {
        did: (
            await db_session.execute(select(Participant).where(Participant.did == did))
        ).scalar_one()
        for did in (api_did, ORG_DID)
    }
    for f in ("dsp_address", "roles", "allowed_scopes", "active"):
        assert getattr(parts[api_did], f) == getattr(parts[ORG_DID], f), f

    creds = {
        did: (
            await db_session.execute(
                select(Credential).where(Credential.subject_did == did)
            )
        ).scalar_one()
        for did in (api_did, ORG_DID)
    }
    for f in ("credential_type", "status", "issuer_did"):
        assert getattr(creds[api_did], f) == getattr(creds[ORG_DID], f), f


@pytest.mark.asyncio
async def test_keycloak_role_in_dataspace_roles_is_refused(db_session, tmp_path):
    """`organization.role` and `dataspace.roles` are different axes.

    The admin API only accepts provider|consumer. A seed that put the Keycloak
    org role here would register a participant the API would have refused, and
    only the CLI-seeded environments would carry it.
    """
    settings = await _seed(db_session, tmp_path)

    outcome = await ops.apply_owner_entry(db_session, settings, _entry(roles=["rec"]))
    await db_session.rollback()

    assert not outcome.ok
    assert "organization.role" in outcome.error


# ── Selecting which entries are ours ──────────────────────────────
#
# A deployment's owners.yaml carries no `dataspace:` block on any entry and its
# schema forbids one, so the block cannot be the selector there. These cover the
# two that replace it, and the errors they refuse to report as skips.


def _owners() -> list[dict]:
    """A deployment-shaped owners file: celine fields only, no `dataspace:`."""
    return [
        {
            "id": "set-distribuzione",
            "name": "SET Distribuzione S.p.A.",
            "did": "did:web:dso.dataspaces.localhost",
            "aliases": ["dso"],
        },
        {
            "id": "greenland",
            "name": "Greenland Soc. Coop.",
            "did": "did:web:rec.dataspaces.localhost",
            "aliases": ["rec"],
        },
        # Attribution metadata for open data: no connector, no DID. It carries a
        # `url`, which `OwnerEntry.canonical_uri` resolves as the canonical id
        # until a DID is set — the `seed/owners.dev.yaml` shape that
        # `owner import` has always accepted (#23).
        {
            "id": "openstreetmap",
            "name": "OpenStreetMap",
            "url": "https://www.openstreetmap.org",
        },
        # Neither a did nor a url: nothing to resolve it by at all.
        {"id": "nameless-consortium", "name": "A Consortium With No Identifiers"},
    ]


def _governance(tmp_path, body: str, name: str = "governance.yaml"):
    import textwrap

    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return path


def test_governance_selects_the_owners_it_names_by_alias(tmp_path):
    """`dso` is a placeholder alias in the open-source pipelines; the file's own
    id is `set-distribuzione`. The registry's id/alias swap is what joins them,
    and it is the reason this selector can read a governance file written by
    somebody who has never seen the deployment's owner registry."""
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.silver.meters_15m:
            ownership:
              - name: dso
            dataspace:
              expose: true
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov])

    assert selection.ok
    assert [e["id"] for e in selection.entries] == ["set-distribuzione"]


def test_the_open_data_owners_are_not_selected(tmp_path):
    """The property the `dataspace:` skip provided, preserved: an owner that is
    attribution metadata is left alone rather than registered."""
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.gold.a:
            ownership:
              - name: greenland
            dataspace:
              expose: true
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov])

    assert [e["id"] for e in selection.entries] == ["greenland"]


def test_two_governance_files_select_the_union_once_each(tmp_path):
    gov_a = _governance(
        tmp_path,
        """
        sources:
          datasets.gold.a:
            ownership: [{name: dso}]
            dataspace: {expose: true}
    """,
        "a.yaml",
    )
    gov_b = _governance(
        tmp_path,
        """
        sources:
          datasets.gold.b:
            ownership: [{name: dso}]
            dataspace: {expose: true}
          datasets.gold.c:
            ownership: [{name: rec}]
            dataspace: {expose: true}
    """,
        "b.yaml",
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov_a, gov_b])

    assert [e["id"] for e in selection.entries] == ["set-distribuzione", "greenland"]


def test_an_owner_governance_names_and_the_file_does_not_declare_is_an_error(tmp_path):
    """Not a skip. A governance file naming an owner the deployment does not
    declare is a broken deployment, and reporting it as a skip is how it reaches
    production — the run would succeed having onboarded nobody for that dataset."""
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.gold.a:
            ownership: [{name: nobody-here}]
            dataspace: {expose: true}
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov])

    assert not selection.ok
    assert any("nobody-here" in e for e in selection.errors)
    assert selection.entries == []


def test_an_owner_with_a_url_and_no_did_is_selected(tmp_path):
    """#23. `ownership[]` is a list of **owners**, not of participants: the entries
    carry a `type` — `organization` for the participant that operates the
    connector, `consortium` or `DATA_OWNER` for attribution — and demanding a DID
    from every one of them failed the whole run on a weather dataset whose
    co-owner is a consortium.

    `OwnerEntry.canonical_uri` is `did or url`, and `governance.schema.json` says
    `did` *"takes priority over `url` as the canonical @id once set"* — so a `url`
    is a canonical id, not the absence of one. `seed/owners.dev.yaml` ships exactly
    this shape (`open-data-provider`, verified, no DID) and `owner import` accepts
    it."""
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.gold.a:
            ownership: [{name: openstreetmap, type: open_source}]
            dataspace: {expose: true}
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov])

    assert selection.ok
    assert [e["id"] for e in selection.entries] == ["openstreetmap"]
    assert selection.skips == {}


def test_an_owner_with_neither_did_nor_url_is_skipped_not_failed(tmp_path):
    """#23. There is nothing to resolve this owner by, so it is not onboarded —
    but a weather dataset whose consortium has no identifier is not a broken
    deployment, and failing the run is how a correct deployment gets stuck.

    The skip carries its reason, so the operator is told which owner was left out
    and why rather than reading a green run and assuming everything was done."""
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.gold.a:
            ownership:
              - {name: greenland, type: organization}
              - {name: nameless-consortium, type: consortium}
            dataspace: {expose: true}
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov])

    assert selection.ok
    assert selection.errors == []
    assert [e["id"] for e in selection.entries] == ["greenland"]
    assert "nameless-consortium" in selection.skips
    assert "neither did nor url" in selection.skips["nameless-consortium"]


def test_a_run_whose_every_owner_is_skipped_does_not_report_an_empty_selection(
    tmp_path,
):
    """The "nothing would be onboarded" error exists so a silent empty selection
    is not read as "no organisations needed". A run that skipped every owner *for a
    stated reason* has already answered that question, and adding the error on top
    would turn the reported skip back into the run failure #23 removed."""
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.gold.a:
            ownership: [{name: nameless-consortium, type: consortium}]
            dataspace: {expose: true}
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov])

    assert selection.ok
    assert selection.entries == []
    assert list(selection.skips) == ["nameless-consortium"]


def test_every_error_is_reported_in_one_pass(tmp_path):
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.gold.a:
            ownership: [{name: nobody-here}]
            dataspace: {expose: true}
          datasets.gold.b:
            ownership: [{name: also-not-here}]
            dataspace: {expose: true}
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov])

    assert len(selection.errors) == 2


def test_a_governance_file_exposing_nothing_is_an_error_not_an_empty_run(tmp_path):
    """ "Nothing would be onboarded" and "no organisations needed" are different
    answers, and a silent empty selection returns the first as the second."""
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.bronze.raw:
            ownership: [{name: dso}]
            dataspace: {expose: false}
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov])

    assert not selection.ok
    assert selection.entries == []


def test_a_governance_path_that_does_not_resolve_is_reported_not_raised(tmp_path):
    """These paths come from chart values now — `bootstrap.orgApply.governance` —
    so a typo in a deployment's values must read like every other selection error
    and reach the operator through the one-pass report, not as a traceback out of
    an init container."""
    missing = tmp_path / "typo.yaml"

    selection = ops.select_entries(_owners(), governance_paths=[missing])

    assert not selection.ok
    assert selection.entries == []
    assert any(str(missing) in e for e in selection.errors)


def test_an_unparseable_governance_file_is_reported_alongside_a_readable_one(
    tmp_path,
):
    """One bad file does not hide the rest: the run collects both and the
    operator fixes them in one pass, which is what every other error here does."""
    broken = tmp_path / "broken.yaml"
    broken.write_text("sources: [this is a list, not a mapping]\n")
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.gold.grid:
            ownership: [{name: nobody-declares-this}]
            dataspace: {expose: true}
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[broken, gov])

    assert not selection.ok
    assert len(selection.errors) == 2
    assert any("broken.yaml" in e for e in selection.errors)
    assert any("nobody-declares-this" in e for e in selection.errors)


def test_without_governance_the_selector_is_carrying_a_did():
    """Unchanged by #23, and that is the point of asserting it here. The
    governance selector now accepts a `url` as a canonical id; this one still
    selects on `did` alone, because without a governance file there is nothing
    saying an owner is *named* by the deployment — `openstreetmap` carries a url
    and is still not onboarded."""
    selection = ops.select_entries(_owners(), governance_paths=None)

    assert selection.ok
    assert [e["id"] for e in selection.entries] == ["set-distribuzione", "greenland"]


# ── Per-run evidence ──────────────────────────────────────────────


@pytest.mark.rule("P-1")
@pytest.mark.asyncio
async def test_run_evidence_onboards_an_entry_with_no_dataspace_block(
    db_session, tmp_path
):
    """Steps 1 and 2 only, and that is the whole requirement of
    `GET /owners/resolve`: a verified owner holding its `did` and `aliases`."""
    settings = await _seed(db_session, tmp_path)
    entry = _owners()[0]

    outcome = await ops.apply_owner_entry(
        db_session,
        settings,
        entry,
        ops.RunEvidence(
            verified_by="demo3-deployment", evidence_ref="recs/owners.yaml@abc1234"
        ),
    )

    assert outcome.ok and outcome.applied
    steps = {s.step: s.action for s in outcome.steps}
    assert steps["application"] == "created"
    assert steps["verification"] == "created"
    # A run flag cannot assert an agreement acceptance or a DSP address.
    assert steps["agreement"] == "skipped"
    assert steps["credential"] == "skipped"
    assert steps["participant"] == "skipped"

    owner = (await db_session.execute(select(Owner))).scalars().one()
    assert owner.id == "set-distribuzione"
    assert owner.did == "did:web:dso.dataspaces.localhost"
    assert owner.aliases == ["dso"]
    assert owner.status == "verified"
    assert owner.verified_by == "demo3-deployment"


@pytest.mark.asyncio
async def test_run_evidence_never_overwrites_the_entrys_own_evidence(
    db_session, tmp_path
):
    """The trap the flags open, and the guard for it.

    A per-entry block says `ops@example.test / TICKET-42`; a later run passing
    `--verified-by demo3-deployment` must not rewrite that to the generic string,
    which would silently downgrade the evidence behind an issued credential.
    Free verification is the state T30 closed; this is the same hole from the
    other side.
    """
    settings = await _seed(db_session, tmp_path)

    first = await ops.apply_owner_entry(db_session, settings, _entry())
    assert first.ok
    await db_session.commit()

    # The same organisation, now reached through a deployment file with no block.
    plain = {
        "id": ALIAS,
        "name": "Example Community",
        "did": ORG_DID,
        "aliases": ["example-c"],
    }
    second = await ops.apply_owner_entry(
        db_session,
        settings,
        plain,
        ops.RunEvidence(verified_by="demo3-deployment", evidence_ref="owners.yaml"),
    )
    await db_session.commit()

    assert second.ok
    owner = (await db_session.execute(select(Owner))).scalars().one()
    assert owner.verified_by == "ops@example.test"
    app = (
        (
            await db_session.execute(
                select(OrganizationApplication).where(
                    OrganizationApplication.alias == ALIAS
                )
            )
        )
        .scalars()
        .one()
    )
    assert app.verified_by == "ops@example.test"
    assert app.evidence_ref == "TICKET-42"

    verification = next(s for s in second.steps if s.step == "verification")
    assert verification.action == "unchanged"
    assert "kept existing evidence" in verification.detail


@pytest.mark.asyncio
async def test_run_evidence_does_not_overwrite_an_owner_seeded_by_owner_import(
    db_session, tmp_path
):
    """#26 — the same guard, on the shape the test above cannot reach.

    `test_run_evidence_never_overwrites_the_entrys_own_evidence` creates the owner
    through `apply_owner_entry`, so it always has an `OrganizationApplication` and
    the guard reading `app_row.verified_by` fires. An owner created by
    `ir-cli owner import` has **no application at all**: `app_row` was created
    fresh in the run carrying `verified_by = None`, the guard never fired, and the
    run's generic string was written over the seed's own claim.

    **This is the chart bootstrap's own sequence** — `owner import`, then
    `org apply` — so every deployment setting `bootstrap.orgApply.verifiedBy`
    rewrote the evidence of every owner its seed had already verified.

    Both fields are asserted: `evidence_ref` was not guarded at all, so keeping
    `verified_by` alone left the name kept and the reference behind it replaced —
    the two halves of one claim coming from different runs.
    """
    settings = await _seed(db_session, tmp_path)

    # The `owner import` shape: an Owner row and no application beside it.
    db_session.add(
        Owner(
            id=ALIAS,
            type="schema:Organization",
            name="Example Community Cooperative",
            did=ORG_DID,
            status="verified",
            verified_by="dev-seed",
            evidence_ref="owners.dev.yaml",
            verified_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await db_session.commit()
    assert (
        await db_session.execute(
            select(func.count()).select_from(OrganizationApplication)
        )
    ).scalar() == 0

    outcome = await ops.apply_owner_entry(
        db_session,
        settings,
        {"id": ALIAS, "name": "Example Community", "did": ORG_DID},
        ops.RunEvidence(
            verified_by="demo3-dataspace-prod", evidence_ref="env/prod/owners.yaml"
        ),
    )
    await db_session.commit()

    assert outcome.ok
    owner = (
        (await db_session.execute(select(Owner).where(Owner.id == ALIAS)))
        .scalars()
        .one()
    )
    assert owner.verified_by == "dev-seed"
    assert owner.evidence_ref == "owners.dev.yaml"

    # And the report agrees with the database. `unchanged` printed this run's own
    # flag, so the one line an operator checks was the line that hid the overwrite.
    verification = next(s for s in outcome.steps if s.step == "verification")
    assert verification.action == "unchanged"
    assert "dev-seed" in verification.detail
    assert "demo3-dataspace-prod" not in verification.detail


@pytest.mark.rule("P-4")
@pytest.mark.asyncio
async def test_a_second_run_with_the_same_evidence_is_a_no_op(db_session, tmp_path):
    """The guard must not turn re-running the deploy-time invocation into a
    report of a change that did not happen."""
    settings = await _seed(db_session, tmp_path)
    entry = _owners()[1]
    evidence = ops.RunEvidence(verified_by="demo3-deployment", evidence_ref="o.yaml")

    first = await ops.apply_owner_entry(db_session, settings, entry, evidence)
    await db_session.commit()
    second = await ops.apply_owner_entry(db_session, settings, entry, evidence)
    await db_session.commit()

    assert first.changed
    assert not second.changed
    assert (
        await db_session.execute(select(func.count()).select_from(Owner))
    ).scalar_one() == 1


@pytest.mark.asyncio
async def test_run_evidence_does_not_blank_a_legal_identity_it_cannot_carry(
    db_session, tmp_path
):
    """The second trap the flags open, found by running the first one's test.

    A deployment's owners.yaml has no registration number, no country codes and
    no participant role. A synthesised block reports them as ``None``, and every
    one of those was being written — so applying a deployment file over an
    organisation ds already knew would have blanked its legal identity. In
    practice it raised `409` instead, because the intake refuses to change a
    verified application's legal fields, which means the run failed rather than
    quietly destroying data. Either way it could not be used for what it exists
    for.
    """
    settings = await _seed(db_session, tmp_path)
    await ops.apply_owner_entry(db_session, settings, _entry())
    await db_session.commit()

    plain = {"id": ALIAS, "name": "Example Community", "did": ORG_DID}
    outcome = await ops.apply_owner_entry(
        db_session,
        settings,
        plain,
        ops.RunEvidence(verified_by="demo3-deployment"),
    )
    await db_session.commit()

    assert outcome.ok, outcome.error
    app = (
        (
            await db_session.execute(
                select(OrganizationApplication).where(
                    OrganizationApplication.alias == ALIAS
                )
            )
        )
        .scalars()
        .one()
    )
    assert app.registration_number == "IT12345678901"
    assert app.registration_type == "vatID"
    assert app.hq_country_code == "IT-TN"
    assert app.legal_name == "Example Community Cooperative"
    assert app.roles == ["consumer"]


@pytest.mark.asyncio
async def test_a_first_run_still_writes_a_complete_row(db_session, tmp_path):
    """Omitting keys must not leave a fresh application half-built: `defaults`
    applies on create, so the name and role are there even though neither is
    sent as a field."""
    settings = await _seed(db_session, tmp_path)

    await ops.apply_owner_entry(
        db_session,
        settings,
        _owners()[1],
        ops.RunEvidence(verified_by="demo3-deployment"),
    )
    await db_session.commit()

    app = (
        (
            await db_session.execute(
                select(OrganizationApplication).where(
                    OrganizationApplication.alias == "greenland"
                )
            )
        )
        .scalars()
        .one()
    )
    assert app.legal_name == "Greenland Soc. Coop."
    assert app.roles == ["consumer"]
    assert app.did == "did:web:rec.dataspaces.localhost"


# ── The CLI guard ─────────────────────────────────────────────────


def test_governance_without_verified_by_is_refused(tmp_path):
    """Refused, not ignored.

    `--governance` selects entries that carry no `dataspace:` block, and such an
    entry without run evidence is skipped. So the two flags apart would select
    exactly the right organisations, skip every one of them, and report a
    successful run that onboarded nobody — the silent no-op this whole plan
    exists because of.
    """
    from typer.testing import CliRunner

    from identity_registry.cli.main import app as cli

    owners = tmp_path / "owners.yaml"
    owners.write_text("owners:\n  - id: dso\n    did: did:web:dso.example\n")
    gov = tmp_path / "governance.yaml"
    gov.write_text("sources: {}\n")

    result = CliRunner().invoke(
        cli, ["org", "apply", "--file", str(owners), "--governance", str(gov)]
    )

    assert result.exit_code == 2
    assert "--verified-by" in result.output


# ── The skip reason names the selector's decision ─────────────────


def test_the_governance_selector_reports_its_own_reason(tmp_path):
    """A skip that reports the wrong reason sends the reader to the wrong file.

    Every entry here also lacks a `dataspace:` block, so "no dataspace: block" is
    *true* of each of them and is the reason for none. The entry that proves the
    difference is `greenland`: it carries a DID, it is perfectly registerable, and
    it is out purely because nothing exposed names it.
    """
    gov = _governance(
        tmp_path,
        """
        sources:
          datasets.silver.meters_15m:
            ownership:
              - name: dso
            dataspace:
              expose: true
    """,
    )

    selection = ops.select_entries(_owners(), governance_paths=[gov])

    assert selection.skipped_reason == "governance does not name it"
    assert [e["id"] for e in selection.entries] == ["set-distribuzione"]


def test_the_did_selector_reports_its_own_reason():
    selection = ops.select_entries(_owners(), governance_paths=None)

    assert selection.skipped_reason == "carries no did"


@pytest.mark.asyncio
async def test_run_evidence_skip_names_the_selector_not_the_missing_block(
    db_session, tmp_path
):
    settings = await _seed(db_session, tmp_path)
    entry = {"id": "greenland", "name": "Greenland", "did": "did:web:g.example.org"}

    outcome = await ops.apply_owner_entry(
        db_session,
        settings,
        entry,
        None,
        skip_reason="governance does not name it",
    )

    assert outcome.applied is False
    assert [s.detail for s in outcome.steps] == ["governance does not name it"]


@pytest.mark.asyncio
async def test_without_run_evidence_the_missing_block_is_still_the_reason(
    db_session, tmp_path
):
    """The flagless invocation every current caller uses. Without evidence a
    `dataspace:` block is the only way in, so its absence really is the reason —
    and passing no `skip_reason` must leave that message exactly as it was."""
    settings = await _seed(db_session, tmp_path)
    entry = {"id": "other-consumer", "name": "Someone Else"}

    outcome = await ops.apply_owner_entry(db_session, settings, entry)

    assert outcome.applied is False
    assert [s.detail for s in outcome.steps] == ["no dataspace: block"]
