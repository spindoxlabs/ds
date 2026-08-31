"""The bundle handed to a verified organisation.

**It used to carry an identity** — an STS secret this registry minted, and
`sts_token_url` / `credential_service_url` pointing at the anchor — so the tests
below were about *rotation*: how to hand over a credential safely. `DID-10`
removed the credential, and with it the question.

What matters now is the opposite property: that the bundle contains **nothing
belonging to an identity the recipient should have generated**, and that the
config it renders points at the recipient's own host rather than ours. Several
tests here are therefore inverted rather than adjusted, and each says so.
"""

from __future__ import annotations

import pytest
from conftest import make_headers

from identity_registry.db.models import EnrolmentToken, Owner, Participant
from identity_registry.services.crypto import hash_sts_secret

PROMOTE = make_headers(scope="identity-registry.organizations.promote")
WRITE = make_headers(scope="identity-registry.organizations.write")

ALIAS = "acme-energy"
DID = "did:web:acme.example.test"


async def _seed(db_session, *, promoted: bool = True) -> None:
    db_session.add(
        Owner(
            id=ALIAS,
            type="organization",
            name="Acme Energy",
            did=DID,
            aliases=[],
            status="verified",
            verified_by="test",
        )
    )
    if promoted:
        db_session.add(
            Participant(
                did=DID,
                dsp_address="https://acme.example.test/protocol/2025-1",
                roles=["consumer"],
                allowed_scopes=["dataspaces.query"],
                sts_client_secret=hash_sts_secret("original-secret"),
            )
        )
        # A counterparty to appear in the bundle.
        db_session.add(
            Participant(
                did="did:web:provider.example.test",
                dsp_address="https://provider.example.test/protocol/2025-1",
                roles=["provider"],
                allowed_scopes=["dataspaces.query"],
                sts_client_secret=hash_sts_secret("other"),
            )
        )
    await db_session.commit()


# ── authorisation ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_alone_cannot_generate_a_bundle(client, db_session):
    """Handing over working credentials is the same class of act as creating a
    counterparty, so it sits on `promote`, not `write`."""
    await _seed(db_session)
    r = await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=WRITE)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_unknown_owner_is_404(client):
    r = await client.post("/admin/owners/nobody/provisioning-bundle", headers=PROMOTE)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_an_unpromoted_organisation_can_still_get_a_bundle(client, db_session):
    """**Inverted.** It used to refuse until the owner was a promoted participant.

    That demanded the outcome as a precondition for the means: the bundle is
    what an organisation configures its deployment *from*, and it becomes a
    participant by enrolling with the code the bundle carries. Requiring
    promotion first was only coherent while the anchor could promote somebody
    into existence on their behalf, which is exactly what `D-51` ends.
    """
    await _seed(db_session, promoted=False)
    r = await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    assert r.status_code == 201
    body = r.json()
    assert body["enrolment"]["code"]
    assert body["participant"]["roles"] == []


@pytest.mark.asyncio
async def test_an_owner_with_no_did_is_refused(client, db_session):
    """The one precondition that survives: there must be a DID to enrol as."""
    db_session.add(
        Owner(
            id="no-did",
            type="organization",
            name="No DID",
            aliases=[],
            status="verified",
            verified_by="test",
        )
    )
    await db_session.commit()
    r = await client.post("/admin/owners/no-did/provisioning-bundle", headers=PROMOTE)
    assert r.status_code == 422


# ── contents ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bundle_carries_what_a_deployment_needs(client, db_session):
    await _seed(db_session)
    r = await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    body = r.json()

    assert body["participant"]["did"] == DID
    assert body["participant"]["roles"] == ["consumer"]

    # What they stand up — every URL on **their** host.
    inst = body["instance"]
    assert inst["role"] == "participant"
    assert inst["participant_did"] == DID
    assert inst["sts_token_url"].startswith("https://acme.example.test/")
    assert inst["credential_service_url"].startswith("https://acme.example.test/")
    assert inst["did_document_url"] == "https://acme.example.test/.well-known/did.json"
    # The two secrets are **named, never valued**: they are the recipient's.
    assert set(inst["secrets_you_must_set"]) == {
        "IDENTITY_REGISTRY_ENCRYPTION_KEY",
        "IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET",
    }

    # Who they trust — the only place the anchor appears.
    assert body["trust"]["trust_anchor_did"].startswith("did:web:")
    assert body["enrolment"]["code"]
    assert "/issuer/credentials" in body["enrolment"]["issuer_url"]

    # The counterparty it will actually negotiate with, not itself.
    assert [c["did"] for c in body["counterparties"]] == [
        "did:web:provider.example.test"
    ]


@pytest.mark.asyncio
async def test_the_bundle_carries_no_identity_of_ours(client, db_session):
    """The whole of `DID-10`, as one assertion.

    Nothing in it is a credential belonging to an identity the recipient should
    have generated, and no URL in it makes our registry their STS or their
    credential store.
    """
    await _seed(db_session)
    body = (
        await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    ).json()

    assert "identity" not in body, "the `identity` block was the defect"
    flat = str(body)
    assert "sts_client_secret" not in flat
    anchor_host = body["trust"]["identity_registry_url"]
    assert body["instance"]["sts_token_url"].startswith("https://acme.example.test")
    assert not body["instance"]["credential_service_url"].startswith(anchor_host)


@pytest.mark.asyncio
async def test_the_enrolment_code_is_real_and_single_use(client, db_session):
    """It is the one thing in the bundle that grants anything — and only with a key."""
    from sqlalchemy import select

    await _seed(db_session)
    body = (
        await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    ).json()

    token = (await db_session.execute(select(EnrolmentToken))).scalars().one()
    assert token.owner_alias == ALIAS
    assert token.redeemed_at is None
    assert token.expires_at is not None
    # Stored as a hash — the bundle is the only copy of the code itself.
    assert token.code_hash != body["enrolment"]["code"]


# ── rotation ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generating_a_bundle_changes_no_ones_identity(client, db_session):
    """**Inverted.** Every call used to rotate the participant's STS secret.

    That was right for a secret only this registry could mint: "send it again"
    could only mean "issue a new one". It no longer mints one, so generating a
    bundle is not a mutation of somebody's identity, and asking twice no longer
    kills the first copy — which was a real operational hazard (three downloads,
    two dead bundles).

    What each call *does* create is a new enrolment code. Codes are single-use,
    so that is additive rather than destructive: reissue is not revocation.
    """
    from sqlalchemy import select

    await _seed(db_session)
    before = (
        (await db_session.execute(select(Participant).where(Participant.did == DID)))
        .scalar_one()
        .sts_client_secret
    )

    first = (
        await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    ).json()
    second = (
        await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    ).json()

    participant = (
        await db_session.execute(select(Participant).where(Participant.did == DID))
    ).scalar_one()
    await db_session.refresh(participant)
    assert participant.sts_client_secret == before, "nothing about the identity moved"

    codes = {first["enrolment"]["code"], second["enrolment"]["code"]}
    assert len(codes) == 2, "each call issues its own single-use code"
    tokens = (await db_session.execute(select(EnrolmentToken))).scalars().all()
    assert len(tokens) == 2
    assert all(t.redeemed_at is None for t in tokens), "reissue is not revocation"


# ── renderers ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_env_format_renders_the_secret(client, db_session):
    await _seed(db_session)
    r = await client.post(
        f"/admin/owners/{ALIAS}/provisioning-bundle?format=env", headers=PROMOTE
    )
    assert r.status_code == 201
    body = r.text
    assert f"CONNECTOR_PARTICIPANT_DID={DID}" in body
    # **Named and left empty** — the recipient chooses it, we do not know it.
    assert "EDC_IAM_STS_OAUTH_CLIENT_SECRET=\n" in body
    assert "IDENTITY_REGISTRY_ENCRYPTION_KEY=\n" in body
    assert "IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET=\n" in body
    # Their instance, their host.
    assert "IDENTITY_REGISTRY_ROLE=participant" in body
    assert "EDC_IAM_STS_OAUTH_TOKEN_URL=https://acme.example.test/" in body
    # Registry questions stay with the anchor.
    assert "CONNECTOR_IDENTITY_REGISTRY_URL=" in body
    # The enrolment code, with the command that redeems it.
    assert "ir-cli participant init --code" in body
    # The default counterparty is filled in from the registry, not left blank.
    assert "CONSUMER_DEFAULT_ASSIGNER=did:web:provider.example.test" in body


@pytest.mark.asyncio
async def test_properties_format_never_contains_a_secret(client, db_session):
    """EDC's FsConfigurationExtension does a plain Properties.load() with no
    interpolation, and properties files get committed. Secrets go in the env."""
    await _seed(db_session)
    r = await client.post(
        f"/admin/owners/{ALIAS}/provisioning-bundle?format=properties", headers=PROMOTE
    )
    assert r.status_code == 201
    body = r.text
    assert f"edc.participant.id={DID}" in body
    assert "secret.alias" in body
    # **Their own host**, not ours. This file was the clearest statement of the
    # centralized model: a generated config telling a participant that its
    # credential service was another organisation's.
    assert "edc.iam.sts.oauth.token.url=https://acme.example.test/" in body
    assert "edc.credential.service.url=https://acme.example.test/" in body
    # And no enrolment code: this file gets committed.
    bundle = (
        await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    ).json()
    assert bundle["enrolment"]["code"] not in body


@pytest.mark.asyncio
async def test_all_format_renders_every_artefact_from_one_code(client, db_session):
    """Three artefacts, one enrolment code between them.

    It used to matter because each call *rotated*: three requests left two dead
    bundles. Nothing rotates now, but the reason survives in a smaller form —
    each call issues a **new single-use code**, so three requests would hand over
    three codes where the recipient needs one.
    """
    await _seed(db_session)
    r = await client.post(
        f"/admin/owners/{ALIAS}/provisioning-bundle?format=all", headers=PROMOTE
    )
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"bundle", "env", "properties"}

    code = body["bundle"]["enrolment"]["code"]
    # All three describe the same handover: the env carries the code the bundle
    # reports, and the properties file — which gets committed — carries none.
    assert code in body["env"]
    assert code not in body["properties"]
    assert f"edc.participant.id={DID}" in body["properties"]


@pytest.mark.asyncio
async def test_unknown_format_is_refused(client, db_session):
    """A typo must not quietly return a different artefact than the one asked
    for — that is how a `.properties` file ends up holding a secret."""
    await _seed(db_session)
    r = await client.post(
        f"/admin/owners/{ALIAS}/provisioning-bundle?format=propertes", headers=PROMOTE
    )
    assert r.status_code == 422


# ── Keycloak posture (KEYCLOAK_MUTATE) ───────────────────────────────────────
#
# Promotion is the one runtime path that *writes* into the realm: it creates
# `svc-ds-connector-<alias>` and hands over the secret. Correct where ds owns the
# realm, and not ds's to do where it is a guest in one somebody else administers.
# The posture used to be inferred from whether admin credentials happened to be
# configured, so these assert that it is now stated and obeyed.


def _settings_with(tmp_path, **overrides):
    from conftest import TEST_DATABASE_URL

    from identity_registry.config import Settings

    return Settings(
        database_url=TEST_DATABASE_URL,
        oidc_issuer_url=None,
        **overrides,
    )


@pytest.mark.asyncio
async def test_guest_posture_never_touches_the_realm(
    client, db_session, monkeypatch, tmp_path
):
    """`KEYCLOAK_MUTATE=false` with admin credentials present must still not write.

    Asserted the hard way — admin credentials *are* configured, so the old
    inferred gate would have opened — and any attempt to authenticate against the
    realm fails the test rather than merely being absent from the response.
    """
    from identity_registry.dependencies import get_settings_dep
    from identity_registry.services import keycloak_admin

    await _seed(db_session)

    client._transport.app.dependency_overrides[get_settings_dep] = lambda: (
        _settings_with(
            tmp_path,
            KEYCLOAK_MUTATE=False,
            KEYCLOAK_ADMIN_URL="http://keycloak.invalid",
            KEYCLOAK_ADMIN_USERNAME="admin",
            KEYCLOAK_ADMIN_PASSWORD="admin",
        )
    )

    async def _forbidden(*a, **k):
        raise AssertionError(
            "promotion authenticated against Keycloak while KEYCLOAK_MUTATE=false"
        )

    monkeypatch.setattr(keycloak_admin.KeycloakAdminClient, "authenticate", _forbidden)

    r = await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    assert r.status_code == 201
    # The bundle is still useful — it just carries no Keycloak block at all. A
    # participant in this posture is given credentials by whoever runs the realm.
    assert "keycloak" not in r.json()


@pytest.mark.asyncio
async def test_owning_posture_provisions_the_client(
    client, db_session, monkeypatch, tmp_path
):
    """The other half: with the posture stated, the client is created and its
    secret reaches the bundle. Without this, the test above would pass just as
    well if provisioning were broken outright."""
    from identity_registry.dependencies import get_settings_dep
    from identity_registry.services import keycloak_admin

    await _seed(db_session)

    client._transport.app.dependency_overrides[get_settings_dep] = lambda: (
        _settings_with(
            tmp_path,
            KEYCLOAK_MUTATE=True,
            KEYCLOAK_ADMIN_URL="http://keycloak.invalid",
            KEYCLOAK_ADMIN_USERNAME="admin",
            KEYCLOAK_ADMIN_PASSWORD="admin",
        )
    )

    created: dict[str, object] = {}

    class FakeAdmin:
        @classmethod
        async def authenticate(cls, *a, **k):
            return cls()

        async def ensure_service_client(
            self, client_id, *, name, scopes, audiences=None
        ):
            created["client_id"] = client_id
            created["scopes"] = scopes
            created["audiences"] = audiences
            return "provisioned-secret"

        async def aclose(self):
            return None

    monkeypatch.setattr(keycloak_admin, "KeycloakAdminClient", FakeAdmin)
    import identity_registry.api.v1.organizations as orgs_api

    monkeypatch.setattr(orgs_api, "KeycloakAdminClient", FakeAdmin)

    r = await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    assert r.status_code == 201
    assert created["client_id"] == f"svc-ds-connector-{ALIAS}"
    # A participant's connector is not a more privileged thing than ours.
    assert "connector.internal" not in created["scopes"]
    assert r.json()["keycloak"]["client_secret"] == "provisioned-secret"


def test_production_guard_flags_realm_admin_on_a_dev_password(monkeypatch):
    """Holding realm-admin rights behind the password `admin` is the footgun the
    posture flag exists to make visible."""
    from ds_auth.production import ProductionGuard

    monkeypatch.setenv("DS_ENV", "production")
    guard = ProductionGuard("identity-registry")
    guard.forbid_default(
        "KEYCLOAK_ADMIN_PASSWORD", "admin", {"admin"}, "set a real password"
    )
    assert [v.setting for v in guard.violations] == ["KEYCLOAK_ADMIN_PASSWORD"]
