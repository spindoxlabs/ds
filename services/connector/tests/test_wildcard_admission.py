"""D-14 — who a wildcard grant admits.

`consumer_id = "*"` means *anyone inside the circle for this offer's controller
and purpose*. It has never meant *anyone at all*, and the rulebook's D-14 row
says so: it "never admits a new controller and never a new purpose".

The purpose half holds; the controller half does not. Both readers — `GET
/internal/consent/check` and `POST /internal/dataplane/authorize` — pass the
requesting consumer straight to `get_granted_subject_ids`, which evaluates
`{consumer_id, WILDCARD_CONSUMER}` and so matches the wildcard row for
*whoever* is asking. `circle.py` is the component that knows a controller from
a processor, and it is consulted only when no consent covers the request, so
the one case it exists for — a party the person was never told about — is the
one case it never sees.

**What is being asserted, and what is deliberately not.** These tests fix the
*behaviour*: an independent controller holding nothing but an offer-scoped
wildcard reads no rows. They do not fix the *mechanism*. How the connector
decides that a DID is the offer's controller — `recipients.controller` is the
alias `example-org`, and resolving an alias to a DID is the owner registry's
job — is Phase 2's to choose, and nothing here constrains it beyond the
outcome.

Three of these pass today and must keep passing; they are the regression half,
and they are why the fix cannot simply be "stop honouring the wildcard".
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.services import circle, subject_identities
from connector.services.agreement_service import upsert_agreement
from connector.services.consent_service import (
    WILDCARD_CONSUMER,
    get_granted_subject_ids,
    set_subject_data_sharing,
)
from tests import make_headers

INTERNAL = make_headers(scope="connector.internal")

GATED = "datasets.silver.meters"
PROVIDER = "did:web:rec.dataspaces.localhost"
SUBJECT = "did:web:rec.dataspaces.localhost:users:sub-001"
PURPOSE = "FlexibilityResearch"
IRI = "https://w3id.org/dsp/policy/purpose/"

# `test-flexibility` in `fixtures/sharing-offers.yaml` names `example-org` as
# its controller. This is the participant behind that alias — the party the
# person consented to, which is the whole point of the offer.
CONTROLLER = "did:web:example-org.dataspaces.localhost"

# An appointed service provider of that controller: inside the circle, admitted
# by `membership: example-org`, disclosed under Art. 13(1)(e) rather than asked.
PROCESSOR = "did:web:service-provider.dataspaces.localhost"

# Somebody else entirely. It holds an accepted agreement and it negotiates for a
# purpose the offer carries, which is precisely what makes it dangerous: every
# check the connector performs today says yes.
INDEPENDENT = "did:web:third-party.dataspaces.localhost"

# Controller of `test-grid-planning`, the *other* consent-based offer on this
# dataset — a stranger to `test-flexibility`, which is what makes admission a
# per-offer question rather than a per-dataset one.
GRID_OPERATOR = "did:web:grid-operator.dataspaces.localhost"


@pytest.fixture(autouse=True)
def _resolvable_subjects(monkeypatch):
    """The data plane filters on registry usernames, not DIDs."""

    async def fake(dids, *_args, **_kwargs):
        return {did: f"user-{did.rsplit(':', 1)[-1]}" for did in dids}

    monkeypatch.setattr(subject_identities, "resolve_usernames", fake)


def _capacity(monkeypatch, capacity: str | None, *, admitted: bool = True):
    """Declare what the identity registry would say about the requester.

    The three network leaves of `circle.py` are stubbed and the module's own
    logic is left to run, so a refactor of `evaluate`, `is_covered_processor` or
    `admits_wildcard` cannot silently turn these green.

    `_controller_did` is the third: `recipients.controller` is the alias
    `example-org` and a requester is a DID, so admission resolves the alias
    through the owner registry. There is none in a unit run — the registry is
    built in `main.create_app` from a configured URL — and an unresolvable
    controller admits nobody by that branch, which would make every test here
    pass for the wrong reason. The live path is covered by the
    `wildcard-admission` e2e flow, which resolves it for real.
    """

    async def _cap(*_args, **_kwargs):
        return capacity

    async def _constraint(*_args, **_kwargs):
        return admitted

    async def _controller(alias, _registry):
        return CONTROLLER if alias == "example-org" else None

    monkeypatch.setattr(circle, "_agreement_capacity", _cap)
    monkeypatch.setattr(circle, "_check_constraint", _constraint)
    monkeypatch.setattr(circle, "_controller_did", _controller)


async def _wildcard_grant(engine):
    """The person shares for the purpose, not with a named counterparty.

    The row stays a wildcard on purpose — `the-members-consent-is-keyed-on-the-
    counterparty` established that keying it on a resolved DID makes a
    withdrawal fail open under D-15. What narrows is who the row admits.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await set_subject_data_sharing(
                session,
                subject_id=SUBJECT,
                dataset_id=GATED,
                consumer_id=WILDCARD_CONSUMER,
                enabled=True,
                purpose=[PURPOSE],
                controller="example-org",
                offer_id="test-flexibility",
            )


async def _agreement(engine, consumer: str, agreement_id: str = "agr-1"):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await upsert_agreement(
                session,
                agreement_id=agreement_id,
                asset_id=GATED,
                consumer_id=consumer,
                provider_id=PROVIDER,
                policy_snapshot={
                    "@type": "odrl:Agreement",
                    "odrl:permission": [
                        {
                            "odrl:action": {"@id": "odrl:use"},
                            "odrl:constraint": [
                                {
                                    "odrl:leftOperand": {"@id": "odrl:purpose"},
                                    "odrl:operator": {"@id": "odrl:isA"},
                                    "odrl:rightOperand": {"@id": f"{IRI}{PURPOSE}"},
                                }
                            ],
                        }
                    ],
                },
                agreed_at=datetime.now(UTC),
            )


async def _check(client, consumer: str) -> dict:
    response = await client.get(
        "/internal/consent/check",
        params={"dataset_id": GATED, "consumer_id": consumer, "purpose": PURPOSE},
        headers=INTERNAL,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _authorize(client, consumer: str) -> dict:
    response = await client.post(
        "/internal/dataplane/authorize",
        json={
            "consumer_did": consumer,
            "agreement_id": "agr-1",
            "dataset_ids": [GATED],
            "purpose": [PURPOSE],
        },
        headers=INTERNAL,
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── the defect ────────────────────────────────────────────────────────────────


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_an_independent_controller_reads_nothing_on_a_wildcard(
    engine, client, monkeypatch
):
    """The consent check must not answer with the subject.

    Consent under Art. 4(11) is consent to a *specific* controller's processing.
    EDPB 05/2020 para 65: other controllers wishing to rely on the original
    consent "should all be named". Nobody named this one, so as far as this
    person's decision goes it is not consented — whatever its agreement says.
    """
    _capacity(monkeypatch, circle.INDEPENDENT_CONTROLLER)
    await _wildcard_grant(engine)

    body = await _check(client, INDEPENDENT)

    assert body["subject_ids"] == []


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_the_data_plane_refuses_an_independent_controller_on_a_wildcard(
    engine, client, monkeypatch
):
    """And the rows must not flow either.

    The two readers are separately pinned because they are separately reachable:
    `dataset-api` calls `authorize` and never calls `check`, so a fix applied to
    one of them would leave the data plane open with the control plane closed.
    """
    _capacity(monkeypatch, circle.INDEPENDENT_CONTROLLER)
    await _wildcard_grant(engine)
    await _agreement(engine, INDEPENDENT)

    body = await _authorize(client, INDEPENDENT)

    assert body["decision"] == "deny"
    assert body["reason"] == "no_consent"


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_the_offer_audience_omits_an_independent_controller_on_a_wildcard(
    engine, client, monkeypatch
):
    """The admin audience read must agree with the check it precedes.

    `GET /consent/admin/shares` is read *before* a disclosure, so listing a
    subject the data plane will then refuse sends the caller to the wrong party,
    and the refusal only shows up later as a parked consent request.
    """
    _capacity(monkeypatch, circle.INDEPENDENT_CONTROLLER)
    await _wildcard_grant(engine)

    response = await client.get(
        "/consent/admin/shares",
        params={"offer_id": "test-flexibility", "consumer_id": INDEPENDENT},
        headers=make_headers(scope="connector.consent.audience"),
    )
    assert response.status_code == 200, response.text
    assert [d["subject_ids"] for d in response.json()["datasets"]] == [[]]

    response = await client.get(
        "/consent/admin/shares",
        params={"offer_id": "test-flexibility", "consumer_id": CONTROLLER},
        headers=make_headers(scope="connector.consent.audience"),
    )
    assert response.status_code == 200, response.text
    assert [d["subject_ids"] for d in response.json()["datasets"]] == [[SUBJECT]]


@pytest.mark.rule("D-5", "D-14")
@pytest.mark.asyncio
async def test_the_offer_audience_omits_a_processor_the_offer_does_not_admit(
    engine, client, monkeypatch
):
    """Capacity is half the circle; the offer's `admitted_by` is the other half.

    The dev consumer holds `capacity: processor` and is not a member of the
    controller, which `test-flexibility`'s `admitted_by` requires. The live
    `onboarding-seam` flow read the audience for exactly that party and expected
    the subject: after #37 the route answers as the data plane does, with nobody.
    Both readers must agree, so both are asserted on the same rows.
    """
    _capacity(monkeypatch, circle.PROCESSOR, admitted=False)
    await _wildcard_grant(engine)

    assert (await _check(client, PROCESSOR))["subject_ids"] == []

    response = await client.get(
        "/consent/admin/shares",
        params={"offer_id": "test-flexibility", "consumer_id": PROCESSOR},
        headers=make_headers(scope="connector.consent.audience"),
    )
    assert response.status_code == 200, response.text
    assert [d["subject_ids"] for d in response.json()["datasets"]] == [[]]


@pytest.mark.rule("D-5", "D-14")
@pytest.mark.asyncio
async def test_the_offer_audience_lists_a_processor_the_offer_admits(
    engine, client, monkeypatch
):
    """The regression half: the bound narrows, it does not close the read."""
    _capacity(monkeypatch, circle.PROCESSOR, admitted=True)
    await _wildcard_grant(engine)

    response = await client.get(
        "/consent/admin/shares",
        params={"offer_id": "test-flexibility", "consumer_id": PROCESSOR},
        headers=make_headers(scope="connector.consent.audience"),
    )
    assert response.status_code == 200, response.text
    assert [d["subject_ids"] for d in response.json()["datasets"]] == [[SUBJECT]]


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_a_joint_controller_reads_nothing_on_a_wildcard(
    engine, client, monkeypatch
):
    """Inside the circle is not the same as covered by the consent.

    A joint controller (Art. 26) satisfies the offer's `admitted_by` and so is
    `inside`, yet `covered_processor` is `inside and capacity == PROCESSOR` —
    it is asked, not admitted. Para 65 draws no distinction between a joint and
    an independent controller: both should be named. This pins that the consent
    path agrees with the path that already gets it right.
    """
    _capacity(monkeypatch, circle.JOINT_CONTROLLER)
    await _wildcard_grant(engine)

    body = await _check(client, INDEPENDENT)

    assert body["subject_ids"] == []


# ── what must not regress ─────────────────────────────────────────────────────


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_the_offers_controller_is_still_admitted(engine, client, monkeypatch):
    """The party the person actually consented to.

    Narrowing the wildcard must not close it. If this goes red the fix has
    stopped honouring offer-scoped consent altogether, which would take
    onboarding's POD-list export with it.
    """
    _capacity(monkeypatch, circle.INDEPENDENT_CONTROLLER)
    await _wildcard_grant(engine)

    body = await _check(client, CONTROLLER)

    assert body["subject_ids"] == [SUBJECT]


@pytest.mark.rule("D-5", "D-14")
@pytest.mark.asyncio
async def test_a_covered_processor_is_still_admitted(engine, client, monkeypatch):
    """A processor acts on the controller's documented instructions.

    The controller has not changed and neither has the processing operation, so
    the person's consent already covers it. Asking again would imply a choice
    that does not exist.
    """
    _capacity(monkeypatch, circle.PROCESSOR)
    await _wildcard_grant(engine)

    body = await _check(client, PROCESSOR)

    assert body["subject_ids"] == [SUBJECT]


@pytest.mark.rule("D-15")
@pytest.mark.asyncio
async def test_a_per_party_grant_still_admits_an_independent_controller(
    engine, client, monkeypatch
):
    """D-15 is the door a new controller comes through, and it stays open.

    This is the whole remedy for what the wildcard stops admitting: the guard
    parks, the person is asked, and the answer is a row naming that party.
    """
    _capacity(monkeypatch, circle.INDEPENDENT_CONTROLLER)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await set_subject_data_sharing(
                session,
                subject_id=SUBJECT,
                dataset_id=GATED,
                consumer_id=INDEPENDENT,
                enabled=True,
                purpose=[PURPOSE],
                controller="example-org",
                offer_id="test-flexibility",
            )

    body = await _check(client, INDEPENDENT)

    assert body["subject_ids"] == [SUBJECT]


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_the_wildcard_row_is_still_written_as_a_wildcard(engine, monkeypatch):
    """The storage shape does not change, only the admission rule.

    `the-members-consent-is-keyed-on-the-counterparty` chose the wildcard row
    deliberately: a grant keyed on a resolved controller DID makes a withdrawal
    fail open under D-15 and forks the member's decision from the
    operator-recorded twin. A fix that narrowed by rewriting the row would
    reintroduce exactly that defect, so this asserts the row itself is untouched
    while `get_granted_subject_ids` keeps answering for the controller.
    """
    _capacity(monkeypatch, circle.INDEPENDENT_CONTROLLER)
    await _wildcard_grant(engine)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        granted = await get_granted_subject_ids(
            session, GATED, CONTROLLER, purpose=[PURPOSE]
        )
        assert granted == [SUBJECT]


# ── the direction that must NOT narrow ────────────────────────────────────────


@pytest.mark.rule("D-14", "D-15a")
@pytest.mark.asyncio
async def test_a_wildcard_withdrawal_still_closes_a_per_party_grant(
    engine, client, monkeypatch
):
    """Grants are aimed; withdrawals spread — and narrowing must not change that.

    `D-14` gates the direction in which a wildcard row **grants**. If it also
    gated the direction in which one **denies**, "you are not inside this circle"
    would quietly become "your withdrawal does not reach here" — the same defect
    pointed the other way, and a worse one: the person clicked stop.

    Here the consumer holds a per-party grant (`D-15`) and is *not* admitted by
    the wildcard. A later blanket withdrawal must still close it (`D-15a`).
    """
    _capacity(monkeypatch, circle.INDEPENDENT_CONTROLLER)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            await set_subject_data_sharing(
                session,
                subject_id=SUBJECT,
                dataset_id=GATED,
                consumer_id=INDEPENDENT,
                enabled=True,
                purpose=[PURPOSE],
                controller="example-org",
                offer_id="test-flexibility",
            )
    assert (await _check(client, INDEPENDENT))["subject_ids"] == [SUBJECT]

    async with factory() as session:
        async with session.begin():
            await set_subject_data_sharing(
                session,
                subject_id=SUBJECT,
                dataset_id=GATED,
                consumer_id=WILDCARD_CONSUMER,
                enabled=False,
                purpose=[PURPOSE],
                controller="example-org",
                offer_id="test-flexibility",
            )

    assert (await _check(client, INDEPENDENT))["subject_ids"] == []


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_an_unresolvable_controller_still_admits_its_processor(
    engine, client, monkeypatch
):
    """The controller branch failing must not take the processor branch with it.

    Whether a requester is a processor comes from what its organisation signed
    and from the offer's own `admitted_by` — neither needs the controller's DID.
    An early return on an unresolvable alias denied a covered processor for a
    reason that had nothing to do with it, which `D-5` rules out. This pins the
    two branches as independent.
    """
    _capacity(monkeypatch, circle.PROCESSOR)

    async def _unresolvable(*_args, **_kwargs):
        return None

    monkeypatch.setattr(circle, "_controller_did", _unresolvable)
    await _wildcard_grant(engine)

    assert (await _check(client, PROCESSOR))["subject_ids"] == [SUBJECT]


@pytest.mark.rule("D-14")
@pytest.mark.asyncio
async def test_admission_is_decided_per_offer_not_per_dataset(
    engine, client, monkeypatch
):
    """A controller is a property of an offer, so admission is too.

    `fixtures/sharing-offers.yaml` puts two consent-based offers on this dataset
    with different controllers: `test-flexibility` is `example-org`'s and
    `test-grid-planning` is `grid-operator`'s. A single verdict for the whole
    dataset would answer the wrong question for one of them — admitting the
    grid operator to the community's offer, or refusing the community its own.
    """
    _capacity(monkeypatch, circle.INDEPENDENT_CONTROLLER)
    await _wildcard_grant(engine)  # example-org's offer only

    # The community's controller reads its own offer's rows.
    assert (await _check(client, CONTROLLER))["subject_ids"] == [SUBJECT]
    # The other offer's controller is a stranger to this one, and gets nothing.
    assert (await _check(client, GRID_OPERATOR))["subject_ids"] == []
