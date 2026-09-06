"""`GET /credentials/check` — does this subject hold a valid credential of this type?

The sibling of `GET /memberships/check`, and the endpoint a sharing offer's
`admitted_by: [{credential_type: ...}]` is evaluated against.

It exists because the connector was asking `GET /admin/credentials` and deciding
validity itself, which failed three ways — two of them *open*. Those three are
pinned below, because widening a grant is the obvious fix and it would have
turned an always-negative check into an always-positive one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from conftest import make_headers
from sqlalchemy.ext.asyncio import async_sessionmaker

from identity_registry.db.models import Credential, Did

SUBJECT = "did:web:rec.dataspaces.localhost:users:data-subject"
OTHER = "did:web:rec.dataspaces.localhost:users:someone-else"
ISSUER = "did:web:registry.dataspaces.localhost"
TYPE = "OrganizationCredential"


@pytest.fixture
def headers():
    """What `svc-ds-connector` actually holds — not `identity-registry.admin`."""
    return make_headers("identity-registry.credentials.read")


@pytest_asyncio.fixture
async def issue(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _issue(
        *,
        subject: str = SUBJECT,
        credential_type: str = TYPE,
        status: str = "active",
        expires_at: datetime | None = None,
        cred_id: str | None = None,
        subject_claims: dict | None = None,
    ):
        async with factory() as session:
            if not await session.get(Did, subject):
                session.add(Did(did=subject, did_type="user"))
                await session.commit()
            session.add(
                Credential(
                    id=cred_id or f"{subject}#{credential_type}#{status}",
                    credential_type=credential_type,
                    issuer_did=ISSUER,
                    subject_did=subject,
                    credential_json={
                        "type": ["VerifiableCredential", credential_type],
                        "credentialSubject": {"id": subject, **(subject_claims or {})},
                    },
                    status=status,
                    expires_at=expires_at,
                )
            )
            await session.commit()

    return _issue


async def _check(client, headers, *, subject: str = SUBJECT, type: str = TYPE):
    return await client.get(
        "/credentials/check",
        params={"subject_did": subject, "type": type},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_an_active_credential_is_held(client, headers, issue):
    await issue()
    body = (await _check(client, headers)).json()
    assert body == {"subject_did": SUBJECT, "credential_type": TYPE, "holds": True}


@pytest.mark.asyncio
async def test_no_credential_at_all_is_not_held(client, headers):
    assert (await _check(client, headers)).json()["holds"] is False


@pytest.mark.asyncio
async def test_the_type_is_applied(client, headers, issue):
    """Failure (2): `GET /admin/credentials` accepts a `type` parameter and
    ignores it, so a subject holding *any* credential answered yes to a question
    about a specific one."""
    await issue(credential_type="DataSubjectCredential")
    assert (await _check(client, headers, type=TYPE)).json()["holds"] is False
    assert (await _check(client, headers, type="DataSubjectCredential")).json()[
        "holds"
    ] is True


@pytest.mark.rule("P-16")
@pytest.mark.asyncio
async def test_a_revoked_credential_is_not_held(client, headers, issue):
    """Failure (3): `CredentialSummary` carries a `status`, never a `revoked`
    field. The connector read `item.get("revoked", False)` — `False` for every
    entry — so the existence of one satisfied the check whatever its state."""
    await issue(status="revoked")
    assert (await _check(client, headers)).json()["holds"] is False


@pytest.mark.rule("P-14")
@pytest.mark.asyncio
async def test_an_expired_credential_is_not_held(client, headers, issue):
    await issue(expires_at=datetime.now(UTC) - timedelta(days=1))
    assert (await _check(client, headers)).json()["holds"] is False


@pytest.mark.asyncio
async def test_an_unexpired_credential_is_held(client, headers, issue):
    await issue(expires_at=datetime.now(UTC) + timedelta(days=1))
    assert (await _check(client, headers)).json()["holds"] is True


@pytest.mark.asyncio
async def test_one_valid_among_several_is_enough(client, headers, issue):
    await issue(status="revoked", cred_id="revoked-one")
    await issue(status="active", cred_id="active-one")
    assert (await _check(client, headers)).json()["holds"] is True


@pytest.mark.rule("P-14")
@pytest.mark.asyncio
async def test_another_subjects_credential_is_not_this_subjects(client, headers, issue):
    await issue(subject=OTHER)
    assert (await _check(client, headers)).json()["holds"] is False


# ── the grant ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_narrow_read_is_enough(client, issue):
    """Failure (1): the roster route needs `identity-registry.admin`, which
    `clients.yaml` refuses a service client — so the connector's check 403'd
    every time. This route is reachable with what the connector holds."""
    await issue()
    r = await _check(client, make_headers("identity-registry.credentials.read"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_admin_still_satisfies_it(client, issue):
    await issue()
    r = await _check(client, make_headers("identity-registry.admin"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_a_neighbouring_read_grant_is_not_enough(client, issue):
    """`identity-registry.read` is the participant registry, not this."""
    await issue()
    r = await _check(client, make_headers("identity-registry.read"))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_it_is_not_open(client, issue):
    await issue()
    r = await client.get(
        "/credentials/check", params={"subject_did": SUBJECT, "type": TYPE}
    )
    assert r.status_code in (401, 403)


# ── claim filtering: an offer restricted to prosumers ─────────────
#
# A community role is a claim on a person's `DataSubjectCredential`, not a
# credential type, so `admitted_by: [{credential_claim: ...}]` needs the
# comparison done here — where `status` says which credential is *current*.


async def _check_claim(client, headers, *, claim=None, value=None, type=TYPE):
    params = {"subject_did": SUBJECT, "type": type}
    if claim is not None:
        params["claim"] = claim
    if value is not None:
        params["value"] = value
    return await client.get("/credentials/check", params=params, headers=headers)


@pytest.mark.asyncio
@pytest.mark.rule("D-55")
async def test_a_matching_claim_is_held(client, headers, issue):
    await issue(subject_claims={"communityRole": "prosumer"})
    body = (
        await _check_claim(client, headers, claim="communityRole", value="prosumer")
    ).json()
    assert body["holds"] is True


@pytest.mark.asyncio
@pytest.mark.rule("D-55")
async def test_a_different_claim_value_is_not_held(client, headers, issue):
    await issue(subject_claims={"communityRole": "consumer"})
    body = (
        await _check_claim(client, headers, claim="communityRole", value="prosumer")
    ).json()
    assert body["holds"] is False


@pytest.mark.asyncio
@pytest.mark.rule("D-55")
async def test_a_credential_without_the_claim_is_not_held(client, headers, issue):
    """An absent claim is not a wildcard. Defaulting it in the admitting
    direction is the exact class of the defect this endpoint was built to
    replace."""
    await issue()
    body = (
        await _check_claim(client, headers, claim="communityRole", value="prosumer")
    ).json()
    assert body["holds"] is False


@pytest.mark.asyncio
@pytest.mark.rule("D-55")
async def test_a_suspended_credential_does_not_satisfy_a_claim(client, headers, issue):
    """**What makes a role transition work.** A superseded credential still says
    `communityRole: consumer` in signed JSON nobody can alter; the register is
    what says it is no longer current, and `status` is how that verdict reaches
    this query."""
    await issue(
        status="suspended",
        cred_id="superseded",
        subject_claims={"communityRole": "prosumer"},
    )
    body = (
        await _check_claim(client, headers, claim="communityRole", value="prosumer")
    ).json()
    assert body["holds"] is False


@pytest.mark.asyncio
@pytest.mark.rule("D-55")
async def test_the_successor_answers_and_the_predecessor_does_not(
    client, headers, issue
):
    """The pair, as a transition leaves them: one suspended `consumer`, one
    active `prosumer`. Both claims are asked and only the current one holds."""
    await issue(
        status="suspended", cred_id="old", subject_claims={"communityRole": "consumer"}
    )
    await issue(
        status="active", cred_id="new", subject_claims={"communityRole": "prosumer"}
    )
    prosumer = (
        await _check_claim(client, headers, claim="communityRole", value="prosumer")
    ).json()
    consumer = (
        await _check_claim(client, headers, claim="communityRole", value="consumer")
    ).json()
    assert prosumer["holds"] is True
    assert consumer["holds"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim", "value"), [("communityRole", None), (None, "prosumer")]
)
@pytest.mark.rule("D-55")
async def test_a_half_specified_claim_filter_is_refused(
    client, headers, issue, claim, value
):
    """Not ignored. Reading a lone `claim` as "any value" turns a narrow question
    into a broad one, at the endpoint that decides admission."""
    await issue(subject_claims={"communityRole": "prosumer"})
    r = await _check_claim(client, headers, claim=claim, value=value)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_no_claim_filter_still_answers_the_type_question(client, headers, issue):
    """Every existing caller sends neither parameter and must be unaffected."""
    await issue(subject_claims={"communityRole": "prosumer"})
    assert (await _check(client, headers)).json()["holds"] is True
