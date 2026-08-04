"""Conformity assessment — `DSSC-TRF-02`, `-03`, `-04`.

The blueprint's requirement is that the rulebook support **automated conformity
assessment** and that something check participants against it. What existed was
`task compliance:validate`, which checks a *governance file* against the ODRL
profile — a different question about a different artefact, sharing most of a name.

The distinction these tests exist to hold:

**Onboarding decides whether a party may join; conformity asks whether it still
qualifies.** The two drift apart with nobody acting — a credential expires, an
agreement version is superseded, a provider stops publishing a DSP address. Every
test below is one of those drifts, and each one passes an onboarding check.
"""
from __future__ import annotations

import textwrap
from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_headers, register_enrolled

from identity_registry.config import Settings
from identity_registry.db.models import (
    Agreement,
    AgreementAcceptance,
    Credential,
    Owner,
    Participant,
)
from identity_registry.services import conformity

READ = make_headers(scope="identity-registry.read")
PROVIDER_DID = "did:web:rec.dataspaces.localhost"

CRITERIA = """
criteria:
  - name: every participant
    required_credentials: [MembershipCredential]
    required_agreement: dataspace-participation
    required_agreement_version: "1.0"
    require_verified_owner: true
  - name: provider
    applies_to: [provider]
    require_dsp_address: true
"""


def settings() -> Settings:
    return Settings(_env_file=None, oidc_issuer_url=None)


@pytest.fixture
def criteria_file(tmp_path):
    p = tmp_path / "conformity.yaml"
    p.write_text(textwrap.dedent(CRITERIA))
    return p


async def seed_participant(
    db,
    did: str = PROVIDER_DID,
    *,
    roles=("provider",),
    dsp: str | None = "http://provider.test/protocol",
    owner_status: str = "verified",
    credential: str | None = "MembershipCredential",
    expires_in_days: int | None = 365,
    accepted_version: str | None = "1.0",
) -> Participant:
    """A participant that is conformant unless a keyword says otherwise."""
    await register_enrolled(db, did, roles=list(roles))
    participant = await db.get(Participant, did)
    participant.dsp_address = dsp

    db.add(
        Owner(
            id="example-org",
            type="schema:Organization",
            name="Example",
            did=did,
            status=owner_status,
            verified_by="dev" if owner_status == "verified" else None,
            verified_at=datetime.now(UTC) if owner_status == "verified" else None,
        )
    )
    db.add(
        Agreement(
            id="dataspace-participation",
            version="1.0",
            applies_to=["provider", "consumer"],
            capacity="processor",
            texts={"en": {"path": "x.md", "sha256": "abc"}},
        )
    )
    if credential:
        db.add(
            Credential(
                id=f"urn:uuid:{credential}",
                credential_type=credential,
                issuer_did="did:web:trust-anchor.dataspaces.localhost",
                subject_did=did,
                credential_json={},
                expires_at=(
                    datetime.now(UTC) + timedelta(days=expires_in_days)
                    if expires_in_days is not None
                    else None
                ),
            )
        )
    if accepted_version:
        db.add(
            AgreementAcceptance(
                owner_alias="example-org",
                agreement_id="dataspace-participation",
                agreement_version=accepted_version,
                capacity="processor",
                locale="en",
                text_sha256="abc",
            )
        )
    await db.commit()
    return participant


async def assess(db, criteria_file, **kw) -> conformity.Assessment:
    participant = await seed_participant(db, **kw)
    rules = conformity.load_criteria(criteria_file)
    return await conformity.assess(db, settings(), participant, rules)


# ── the criteria are data, and unreadable criteria are an error ───


def test_criteria_are_read_from_a_file(criteria_file):
    rules = conformity.load_criteria(criteria_file)
    assert [r.name for r in rules] == ["every participant", "provider"]
    assert rules[1].applies_to == ("provider",)
    assert rules[1].require_dsp_address is True


def test_a_missing_criteria_file_is_an_error(tmp_path):
    """Not an empty rule set. A conformity report generated without criteria
    would say every participant conforms to nothing in particular — the one
    output worse than "unknown"."""
    with pytest.raises(conformity.ConformityError) as exc:
        conformity.load_criteria(tmp_path / "nope.yaml")
    assert "no conformity criteria" in str(exc.value)


def test_an_empty_criteria_file_is_an_error(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("criteria: []\n")
    with pytest.raises(conformity.ConformityError):
        conformity.load_criteria(p)


# ── the drifts ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_participant_meeting_every_rule_is_conformant(db_session, criteria_file):
    report = await assess(db_session, criteria_file)
    assert report.status == conformity.CONFORMANT
    assert report.failures == []


@pytest.mark.asyncio
async def test_an_expired_credential_is_not_a_held_credential(db_session, criteria_file):
    """The commonest drift, and invisible to anything that checks existence.

    The row is still there and still says `active`; it simply stopped being
    presentable at a moment nobody was watching.
    """
    report = await assess(db_session, criteria_file, expires_in_days=-1)
    assert report.status == conformity.NON_CONFORMANT
    failure = next(f for f in report.failures if f.rule.endswith("MembershipCredential"))
    assert failure.detail == "expired"


@pytest.mark.asyncio
async def test_a_superseded_agreement_version_is_non_conformant(
    db_session, criteria_file
):
    """Nobody did anything wrong and the participant is no longer covered.

    This is the case the whole check exists for: an acceptance that was valid
    when it was made, against a version that has since been replaced.
    """
    report = await assess(db_session, criteria_file, accepted_version="0.9")
    failure = next(f for f in report.failures if f.rule.startswith("agreement:"))
    assert "accepted ['0.9'], required 1.0" in failure.detail


@pytest.mark.asyncio
async def test_never_accepting_the_agreement_is_reported_differently(
    db_session, criteria_file
):
    """*"Never accepted"* and *"accepted an old version"* are different facts and
    lead to different conversations."""
    report = await assess(db_session, criteria_file, accepted_version=None)
    failure = next(f for f in report.failures if f.rule.startswith("agreement:"))
    assert failure.detail == "never accepted"


@pytest.mark.asyncio
async def test_a_provider_with_no_dsp_address_is_non_conformant(
    db_session, criteria_file
):
    report = await assess(db_session, criteria_file, dsp=None)
    assert any(f.rule == "dsp" for f in report.failures)


@pytest.mark.asyncio
async def test_a_consumer_is_not_asked_for_a_dsp_address(db_session, criteria_file):
    """`applies_to` is why: a consumer initiates and has nothing to be reached
    at, so requiring an address of it would be a rule nobody could satisfy."""
    report = await assess(
        db_session, criteria_file, roles=("consumer",), dsp=None,
        did="did:web:third-party.dataspaces.localhost",
    )
    assert report.status == conformity.CONFORMANT


@pytest.mark.asyncio
async def test_an_unverified_owner_is_non_conformant(db_session, criteria_file):
    report = await assess(db_session, criteria_file, owner_status="suspended")
    failure = next(f for f in report.failures if f.rule == "owner")
    assert "suspended" in failure.detail


@pytest.mark.asyncio
async def test_a_deactivated_participant_is_reported_not_skipped(
    db_session, criteria_file
):
    """A deactivated participant is exactly the one an auditor asks about."""
    participant = await seed_participant(db_session)
    participant.active = False
    await db_session.commit()

    rules = conformity.load_criteria(criteria_file)
    reports = await conformity.assess_all(db_session, settings(), rules)
    assert len(reports) == 1
    assert any(f.rule == "active" for f in reports[0].failures)


@pytest.mark.asyncio
async def test_a_participant_no_criterion_covers_is_a_finding(db_session, tmp_path):
    """Silence would be the wrong answer.

    A participant held to no stated standard was admitted on terms nobody wrote
    down — a finding about the *criteria*, and one that a check reporting only
    per-rule results would swallow.
    """
    p = tmp_path / "c.yaml"
    p.write_text("criteria:\n  - name: providers only\n    applies_to: [provider]\n")
    report = await assess(
        db_session, p, roles=("observer",), did="did:web:observer.test"
    )
    assert report.status == conformity.NON_CONFORMANT
    assert report.failures[0].rule == "criteria"


# ── the report, and the route ─────────────────────────────────────


@pytest.mark.asyncio
async def test_the_report_says_what_it_answers(db_session, criteria_file):
    rules = conformity.load_criteria(criteria_file)
    reports = await conformity.assess_all(db_session, settings(), rules)
    body = conformity.render(reports, settings())
    assert body["type"] == "ConformityReport"
    assert set(body["conformsTo"]) == {"DSSC-TRF-02", "DSSC-TRF-03", "DSSC-TRF-04"}
    assert body["summary"]["participants"] == len(reports)


def _with_criteria(client, path):
    """Point the app at a criteria file.

    Through the **dependency override**, not the environment: the `client`
    fixture pins one `Settings` instance for the app, so an env var set later
    reaches the CLI and nothing the route reads. A test that set one and passed
    would be passing on the repository's real `seed/conformity.dev.yaml`, which
    is present relative to the test's working directory — the quietest possible
    way to assert nothing.
    """
    from identity_registry.dependencies import get_settings_dep

    current = client._transport.app.dependency_overrides[get_settings_dep]()
    patched = current.model_copy(update={"conformity_criteria_path": str(path)})
    client._transport.app.dependency_overrides[get_settings_dep] = lambda: patched
    return patched


@pytest.mark.asyncio
async def test_the_route_serves_the_report(client, db_session, criteria_file):
    _with_criteria(client, criteria_file)
    await seed_participant(db_session)
    body = (await client.get("/admin/conformity", headers=READ)).json()
    assert body["summary"]["conformant"] == 1
    assert body["participants"][0]["did"] == PROVIDER_DID


@pytest.mark.asyncio
async def test_the_route_refuses_when_the_criteria_cannot_be_read(client, db_session):
    """**503, not an empty pass.** A report with no criteria behind it would be
    a clean bill of health nobody issued."""
    _with_criteria(client, "/nope/nope.yaml")
    r = await client.get("/admin/conformity", headers=READ)
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_the_route_needs_a_scope(client):
    from conftest import make_headers as mh

    r = await client.get(
        "/admin/conformity", headers=mh(scope="identity-registry.nothing")
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_assessment_changes_nothing(db_session, criteria_file):
    """Suspension is a decision. One an automated check makes for you is a
    decision nobody made — so this reads, and produces the evidence for it."""
    participant = await seed_participant(db_session, dsp=None)
    rules = conformity.load_criteria(criteria_file)
    report = await conformity.assess(db_session, settings(), participant, rules)
    assert report.status == conformity.NON_CONFORMANT

    await db_session.refresh(participant)
    assert participant.active is True, "a failing assessment must not deactivate"
