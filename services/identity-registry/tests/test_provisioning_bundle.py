"""The connection bundle handed to a promoted organisation.

It carries working credentials, so its refusals and its rotation behaviour matter
more than its contents.
"""
from __future__ import annotations

import pytest
from conftest import make_headers

from identity_registry.db.models import Owner, Participant
from identity_registry.services.crypto import hash_sts_secret, verify_sts_secret

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
async def test_refuses_before_promotion(client, db_session):
    """A bundle for something nobody can negotiate with is a support ticket."""
    await _seed(db_session, promoted=False)
    r = await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)
    assert r.status_code == 409
    assert "promote it first" in r.json()["detail"]


# ── contents ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bundle_carries_what_a_deployment_needs(client, db_session):
    await _seed(db_session)
    body = (await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)).json()

    assert body["participant"]["did"] == DID
    assert body["participant"]["roles"] == ["consumer"]

    identity = body["identity"]
    assert identity["sts_client_id"] == DID
    assert identity["sts_client_secret"]
    assert DID in identity["did_document_url"]
    assert DID in identity["credential_service_url"]

    assert body["trust"]["trust_anchor_did"].startswith("did:web:")
    # The counterparty it will actually negotiate with, not itself.
    assert [c["did"] for c in body["counterparties"]] == ["did:web:provider.example.test"]


# ── rotation ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generating_rotates_the_sts_secret(client, db_session):
    """The registry stores a hash and cannot re-show a secret, so "send it again"
    can only mean "issue a new one". That is also what makes a leaked bundle
    invalidatable."""
    await _seed(db_session)

    first = (await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)).json()
    second = (await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)).json()

    a = first["identity"]["sts_client_secret"]
    b = second["identity"]["sts_client_secret"]
    assert a and b and a != b, "each call must issue a fresh secret"

    # …and the stored hash tracks the latest, so the earlier one is dead.
    # `hash_sts_secret` is salted PBKDF2, so verify rather than re-hash.
    from sqlalchemy import select

    participant = (
        await db_session.execute(select(Participant).where(Participant.did == DID))
    ).scalar_one()
    await db_session.refresh(participant)
    stored = participant.sts_client_secret
    assert verify_sts_secret(b, stored), "the newest secret must be the one that works"
    assert not verify_sts_secret(a, stored), "the previous secret must stop working"
    assert not verify_sts_secret("original-secret", stored)


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
    assert "EDC_IAM_STS_OAUTH_CLIENT_SECRET=" in body
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
    # The literal secret must not appear anywhere in it.
    bundle = (await client.post(f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE)).json()
    assert bundle["identity"]["sts_client_secret"] not in body


@pytest.mark.asyncio
async def test_all_format_renders_every_artefact_in_one_rotation(client, db_session):
    """The operator needs three files and each call rotates.

    Asking three times would hand over two bundles whose secret no longer works,
    so `format=all` is the only shape a UI can offer downloads from.
    """
    await _seed(db_session)
    r = await client.post(
        f"/admin/owners/{ALIAS}/provisioning-bundle?format=all", headers=PROMOTE
    )
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"bundle", "env", "properties"}

    secret = body["bundle"]["identity"]["sts_client_secret"]
    # All three describe the *same* rotation: the env carries the secret the
    # bundle reports, and the properties file still carries none.
    assert f"EDC_IAM_STS_OAUTH_CLIENT_SECRET={secret}" in body["env"]
    assert secret not in body["properties"]
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
        export_base_path=str(tmp_path),
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

    client._transport.app.dependency_overrides[get_settings_dep] = lambda: _settings_with(
        tmp_path,
        KEYCLOAK_MUTATE=False,
        KEYCLOAK_ADMIN_URL="http://keycloak.invalid",
        KEYCLOAK_ADMIN_USERNAME="admin",
        KEYCLOAK_ADMIN_PASSWORD="admin",
    )

    async def _forbidden(*a, **k):
        raise AssertionError(
            "promotion authenticated against Keycloak while KEYCLOAK_MUTATE=false"
        )

    monkeypatch.setattr(keycloak_admin.KeycloakAdminClient, "authenticate", _forbidden)

    r = await client.post(
        f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE
    )
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

    client._transport.app.dependency_overrides[get_settings_dep] = lambda: _settings_with(
        tmp_path,
        KEYCLOAK_MUTATE=True,
        KEYCLOAK_ADMIN_URL="http://keycloak.invalid",
        KEYCLOAK_ADMIN_USERNAME="admin",
        KEYCLOAK_ADMIN_PASSWORD="admin",
    )

    created: dict[str, object] = {}

    class FakeAdmin:
        @classmethod
        async def authenticate(cls, *a, **k):
            return cls()

        async def ensure_service_client(self, client_id, *, name, scopes):
            created["client_id"] = client_id
            created["scopes"] = scopes
            return "provisioned-secret"

        async def aclose(self):
            return None

    monkeypatch.setattr(keycloak_admin, "KeycloakAdminClient", FakeAdmin)
    import identity_registry.api.v1.organizations as orgs_api

    monkeypatch.setattr(orgs_api, "KeycloakAdminClient", FakeAdmin)

    r = await client.post(
        f"/admin/owners/{ALIAS}/provisioning-bundle", headers=PROMOTE
    )
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
