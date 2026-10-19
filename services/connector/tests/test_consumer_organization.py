"""The consumer's organisation, from the credential it presented to the verdict.

Rulebook X-18. EDC verifies the consumer's
`OrganizationCredential` at negotiation (a DEFAULT DCP scope) and stores it on
the provider's agreement; `NegotiationEventPublisher` forwards its
`organizationId`/`organizationType`; the webhook keeps them on the agreement row;
`/internal/dataplane/authorize` re-checks with the issuer that the credential is
still live and emits `organizations` for the PEP's organization layer.

Every way of not knowing the organisation ends the same: an empty list and a
reason, which a PEP reads as no rows on an organization-bound layer.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from ds.governance import DataplaneDecision
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from connector.db.models import ContractAgreementORM
from connector.dependencies import get_db, get_notifier
from connector.main import create_app
from tests import make_headers
from tests.test_dataplane_authorize import (  # noqa: F401 — the autouse stub
    CONSUMER,
    GATED,
    PROVIDER,
    _authorize,
    _consent,
    _resolvable_subjects,
)

WEBHOOK = make_headers(scope="connector.webhook")

ORGANIZATION = "example-org"
OTHER = "other-org"

ORG_MATCH = "datasets.gold.example_rec_measurements"
ORG_TYPED = "datasets.gold.example_dso_feeders"
ORG_ALLOW_ALL = "datasets.gold.example_reference"
RULES = {
    ORG_MATCH: {
        "row_filters": [
            {
                "handler": "organization_match",
                "binds": "organization",
                "args": {"column": "community_id"},
            }
        ]
    },
    ORG_TYPED: {
        "row_filters": [
            {
                "handler": "organization_match",
                "binds": "organization",
                "args": {"column": "dso_id", "org_type": "dso"},
            }
        ]
    },
    ORG_ALLOW_ALL: {"row_filters": [{"handler": "allow_all", "binds": "organization"}]},
}


@pytest.fixture(autouse=True)
def _datasets(monkeypatch):
    from ds.governance.models import GovernanceRuleV2

    from connector.services import consent_vocabulary as vocab

    real = vocab.resolve_dataset

    def resolve(dataset_id: str):
        if dataset_id in RULES:
            return GovernanceRuleV2.model_validate(RULES[dataset_id])
        return real(dataset_id)

    monkeypatch.setattr(vocab, "resolve_dataset", resolve)


@pytest.fixture
def issuer(monkeypatch):
    """The issuer's register: which (DID, organizationId) pairs are live."""
    from connector.services import circle

    live: set[tuple[str, str]] = set()
    asked: list[dict] = []

    async def holds(_url, subject_did, spec, _token_provider=None):
        asked.append({"subject_did": subject_did, **spec})
        return (subject_did, spec["value"]) in live

    monkeypatch.setattr(circle, "_holds_credential_claim", holds)
    return live, asked


@pytest_asyncio.fixture
async def webhook_client(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_notifier] = lambda: None
    app.state.prov = None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def _finalized(
    client,
    *,
    agreement_id: str,
    asset_id: str,
    ids: list[str],
    types: list[str],
    provider: str = PROVIDER,
    consumer: str = CONSUMER,
):
    body = {
        "id": f"evt-{agreement_id}",
        "type": "CONTRACT_NEGOTIATION_FINALIZED",
        "payload": {
            "contractNegotiationId": f"neg-{agreement_id}",
            "contractAgreementId": agreement_id,
            "dspAgreementId": agreement_id,
            "assetId": asset_id,
            "consumerId": consumer,
            "providerId": provider,
            "policy": _purposes_policy(),
            "presentedOrganization": {
                "organizationId": ids,
                "organizationType": types,
            },
        },
    }
    r = await client.post("/webhooks/contract-negotiation", json=body, headers=WEBHOOK)
    assert r.status_code == 200, r.text


def _purposes_policy() -> dict:
    from tests.test_dataplane_authorize import _policy

    return _policy("EnergyCommunityOperation", "FlexibilityResearch", "GridMonitoring")


async def _row(engine, agreement_id: str) -> ContractAgreementORM:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        return (
            await session.execute(
                select(ContractAgreementORM).where(
                    ContractAgreementORM.agreement_id == agreement_id
                )
            )
        ).scalar_one()


async def _verdict(client, agreement_id: str, dataset_id: str, **body) -> dict:
    r = await _authorize(
        client,
        agreement_id=agreement_id,
        dataset_ids=[dataset_id],
        purpose=body.pop("purpose", ["GridMonitoring"]),
        **body,
    )
    assert r.status_code == 200, r.text
    decision = r.json()
    DataplaneDecision.model_validate(decision)
    return decision["datasets"][0]


# ── the webhook ──────────────────────────────────────────────────────────────


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_the_provider_records_the_presented_organisation(engine, webhook_client):
    await _finalized(
        webhook_client,
        agreement_id="agr-1",
        asset_id=ORG_MATCH,
        ids=[ORGANIZATION],
        types=["rec"],
    )
    row = await _row(engine, "agr-1")
    assert row.consumer_organization_id == ORGANIZATION
    assert row.consumer_organization_type == "rec"


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_the_consumer_side_records_nothing(engine, webhook_client):
    """On a consumer the same claims name the provider — not the consumer."""
    await _finalized(
        webhook_client,
        agreement_id="agr-c",
        asset_id=ORG_MATCH,
        ids=[ORGANIZATION],
        types=["rec"],
        provider="did:web:grid-operator.dataspaces.localhost",
        consumer=PROVIDER,
    )
    row = await _row(engine, "agr-c")
    assert row.consumer_organization_id is None
    assert row.consumer_organization_type is None


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_two_presented_organisations_record_none(engine, webhook_client):
    await _finalized(
        webhook_client,
        agreement_id="agr-2",
        asset_id=ORG_MATCH,
        ids=[ORGANIZATION, OTHER],
        types=["rec"],
    )
    row = await _row(engine, "agr-2")
    assert row.consumer_organization_id is None


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_nothing_presented_records_none(engine, webhook_client):
    await _finalized(
        webhook_client, agreement_id="agr-0", asset_id=ORG_MATCH, ids=[], types=[]
    )
    row = await _row(engine, "agr-0")
    assert row.consumer_organization_id is None


# ── the verdict ──────────────────────────────────────────────────────────────


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_the_live_organisation_reaches_the_verdict(
    engine, client, webhook_client, issuer
):
    live, asked = issuer
    live.add((CONSUMER, ORGANIZATION))
    await _finalized(
        webhook_client,
        agreement_id="agr-1",
        asset_id=ORG_MATCH,
        ids=[ORGANIZATION],
        types=["rec"],
    )
    verdict = await _verdict(client, "agr-1", ORG_MATCH)
    assert verdict["decision"] == "allow"
    assert verdict["organizations"] == [ORGANIZATION]
    assert verdict["reason"] is None
    # Asked of the issuer, for this DID, the claim it presented.
    assert asked == [
        {
            "subject_did": CONSUMER,
            "type": "OrganizationCredential",
            "claim": "organizationId",
            "value": ORGANIZATION,
        }
    ]


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_a_credential_retired_since_serves_no_organisation_rows(
    engine, client, webhook_client, issuer
):
    """Suspended or revoked after the agreement — a reissue suspends it (P-30)."""
    await _finalized(
        webhook_client,
        agreement_id="agr-1",
        asset_id=ORG_MATCH,
        ids=[ORGANIZATION],
        types=["rec"],
    )
    verdict = await _verdict(client, "agr-1", ORG_MATCH)
    assert verdict["decision"] == "allow"
    assert verdict["organizations"] == []
    assert verdict["reason"] == "organization_unresolved"


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_an_agreement_with_no_organisation_serves_no_organisation_rows(
    engine, client, webhook_client, issuer
):
    """Agreements made before 4.3 carry none, and none is guessed."""
    await _finalized(
        webhook_client, agreement_id="agr-0", asset_id=ORG_MATCH, ids=[], types=[]
    )
    verdict = await _verdict(client, "agr-0", ORG_MATCH)
    assert verdict["organizations"] == []
    assert verdict["reason"] == "organization_unresolved"
    assert issuer[1] == [], "nothing to ask the issuer about"


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_a_declared_org_type_must_match_the_presented_one(
    engine, client, webhook_client, issuer
):
    live, _ = issuer
    live.add((CONSUMER, ORGANIZATION))
    await _finalized(
        webhook_client,
        agreement_id="agr-t",
        asset_id=ORG_TYPED,
        ids=[ORGANIZATION],
        types=["rec"],
    )
    verdict = await _verdict(client, "agr-t", ORG_TYPED)
    assert verdict["organizations"] == []
    assert verdict["reason"] == "organization_type_mismatch"


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_a_matching_org_type_passes(engine, client, webhook_client, issuer):
    live, _ = issuer
    live.add((CONSUMER, ORGANIZATION))
    await _finalized(
        webhook_client,
        agreement_id="agr-t",
        asset_id=ORG_TYPED,
        ids=[ORGANIZATION],
        types=["dso"],
    )
    verdict = await _verdict(client, "agr-t", ORG_TYPED)
    assert verdict["organizations"] == [ORGANIZATION]
    assert verdict["reason"] is None


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_an_allow_all_organization_layer_needs_no_reason(
    engine, client, webhook_client, issuer
):
    """Nothing narrows on the organization: an unknown one explains nothing."""
    await _finalized(
        webhook_client,
        agreement_id="agr-a",
        asset_id=ORG_ALLOW_ALL,
        ids=[],
        types=[],
    )
    verdict = await _verdict(client, "agr-a", ORG_ALLOW_ALL)
    assert verdict["decision"] == "allow"
    assert verdict["organizations"] == []
    assert verdict["reason"] is None


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_a_consent_gated_dataset_carries_the_organisation_too(
    engine, client, webhook_client, issuer
):
    """The person layer is the consent filter; the organization layer is this."""
    live, _ = issuer
    live.add((CONSUMER, ORGANIZATION))
    await _finalized(
        webhook_client,
        agreement_id="agr-g",
        asset_id=GATED,
        ids=[ORGANIZATION],
        types=["rec"],
    )
    await _consent(engine, purpose=["FlexibilityResearch"])
    verdict = await _verdict(client, "agr-g", GATED, purpose=["FlexibilityResearch"])
    assert verdict["decision"] == "allow"
    assert verdict["row_filter"] is not None
    assert verdict["organizations"] == [ORGANIZATION]


@pytest.mark.rule("X-18")
@pytest.mark.asyncio
async def test_a_refusal_carries_no_organisation(
    engine, client, webhook_client, issuer
):
    live, _ = issuer
    live.add((CONSUMER, ORGANIZATION))
    await _finalized(
        webhook_client,
        agreement_id="agr-g",
        asset_id=GATED,
        ids=[ORGANIZATION],
        types=["rec"],
    )
    # No consent: the dataset is refused, and a refusal names nobody.
    verdict = await _verdict(client, "agr-g", GATED, purpose=["FlexibilityResearch"])
    assert verdict["decision"] == "deny"
    assert verdict["organizations"] is None
