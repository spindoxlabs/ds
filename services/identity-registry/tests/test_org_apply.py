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

import pytest
from conftest import make_headers, register_enrolled
from sqlalchemy import func, select

from identity_registry.config import Settings
from identity_registry.db.models import (
    AgreementAcceptance,
    Credential,
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
        s.detail == "awaiting enrolment"
        for s in outcome.steps
        if s.action == "skipped"
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
    assert (
        await db_session.execute(select(Credential))
    ).scalars().first() is None


@pytest.mark.asyncio
async def test_apply_completes_once_the_organisation_has_enrolled(
    db_session, tmp_path
):
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
async def test_entry_without_dsp_address_stops_at_the_credential(
    db_session, tmp_path
):
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
