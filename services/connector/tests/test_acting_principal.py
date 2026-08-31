"""Who performed an act that determined how data may be processed.

Every other provenance event names the **participant** — which organisation — and
that is enough for a disclosure, where the organisation is the controller. It is
not enough for the acts that decide *what the terms are*: publishing a catalogue
turns `governance.yaml` into ODRL offers, with the purposes and the assigner every
later disclosure is evaluated against.

`DataIngested` carried `provider_did` and `agreement_ref` and no human at all, so
"who published this offer" and "who decided to ingest this" had no answer anywhere
in the system — for exactly the acts that determine purposes. That is a GDPR
Art. 5(2) accountability gap, not a nice-to-have.

The other half of these tests is the constraint: an audit trail is not a reason to
start storing people's names.
"""

from __future__ import annotations

import jwt as pyjwt
import pytest
from ds_auth import Principal

from connector.services.prov_bridge import acting_principal
from tests import _claims
from tests.test_provenance_events import prov_client  # noqa: F401 — shared fixture

ISSUER = "http://keycloak.dataspaces.localhost/realms/dataspaces"


def _human(**extra) -> Principal:
    claims = {
        "sub": "00000000-0000-4000-a000-000000000003",
        "iss": ISSUER,
        "email": "provider@example.test",
        "preferred_username": "provider@example.test",
        "name": "Provider User",
        "given_name": "Provider",
        "family_name": "User",
        "groups": ["ds-participant-admin"],
        **extra,
    }
    return Principal.from_claims(claims)


@pytest.mark.rule("D-2", "L-3")
def test_the_act_names_a_human_pseudonymously():
    acted = acting_principal(_human())
    assert acted["subject"] == "00000000-0000-4000-a000-000000000003"
    assert acted["issuer"] == ISSUER
    assert acted["is_service"] is False


@pytest.mark.rule("D-2", "L-3")
def test_no_personal_data_reaches_the_record():
    """The constraint that keeps this compatible with the rest of the provenance
    model: codes, pseudonymous identifiers and hashes only.

    Asserted over the *rendered* record rather than field by field, so a future
    field cannot quietly reintroduce a name."""
    rendered = repr(acting_principal(_human()))
    for pii in ("provider@example.test", "Provider User", "Provider", "User"):
        assert pii not in rendered, f"{pii!r} leaked into the provenance record"


@pytest.mark.rule("D-2")
def test_a_sub_is_recorded_with_its_issuer():
    """A realm-scoped identifier means nothing without the realm that minted it —
    and an operator resolving it back to a person needs realm access, which is the
    separation this relies on."""
    acted = acting_principal(_human(iss=None))
    assert acted["issuer"] is None
    acted = acting_principal(_human())
    assert acted["issuer"] == ISSUER


def test_a_service_is_recorded_as_a_service():
    """An automated publish must not read as a person's decision."""
    service = Principal.from_claims(
        {
            "sub": "svc",
            "iss": ISSUER,
            "preferred_username": "service-account-svc-ds-e2e",
            "scope": "connector.provider.write",
        }
    )
    assert acting_principal(service)["is_service"] is True


@pytest.mark.rule("D-16")
def test_the_owner_acted_for_is_recorded():
    """ "Acting for whom" is the question an owner-scoped act has to answer."""
    acted = acting_principal(_human(), on_behalf_of="example-org")
    assert acted["on_behalf_of"] == "example-org"


def test_no_principal_yields_no_attribution():
    """An unattributed act is recorded as unattributed, never guessed at."""
    assert acting_principal(None) is None


# ── The record cannot be authored by the party it names ──────────────────────


def _user_headers(sub: str) -> dict:
    token = pyjwt.encode(
        _claims(
            sub=sub,
            iss=ISSUER,
            email="operator@example.test",
            preferred_username="operator@example.test",
            groups=["ds-participant-admin"],
        ),
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.rule("D-16")
@pytest.mark.asyncio
async def test_ingestion_attributes_the_verified_caller_not_the_body(prov_client):
    """The actor comes from the **verified token**, never from the request — so a
    caller cannot record somebody else as having made their decision."""
    client, fake = prov_client

    r = await client.post(
        "/admin/ingestion",
        json={
            "dataset_id": "datasets.silver.meters",
            "source_ref": "handover-2026-07",
            "record_count": 5,
            # A caller claiming to be somebody else. It must not be honoured.
            "acted_by": {"subject": "someone-else", "issuer": ISSUER},
        },
        headers=_user_headers("the-real-caller"),
    )

    assert r.status_code == 200, r.text
    ingested = [kwargs for name, kwargs in fake.calls if name == "data_ingested"]
    assert ingested, f"no data_ingested call: {[n for n, _ in fake.calls]}"
    acted = ingested[0]["acted_by"]
    assert acted["subject"] == "the-real-caller"
    assert acted["is_service"] is False
    # And the body's claim is nowhere in the record.
    assert "someone-else" not in repr(ingested[0])
