"""`circle.py` — evaluating a sharing offer's `admitted_by`.

Two constraint kinds are declared in `sharing-offers.yaml`: `membership` and
`credential_type`. The second one asked a route it could not reach, sent a
parameter that route ignores, and read a field its response has never had.

The three failures compound in opposite directions, which is why they are pinned
separately: the 403 made the check always-negative, and fixing *only* the grant
would have made it always-positive.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from connector.services.circle import _check_constraint

REGISTRY = "http://identity-registry.test"
SUBJECT = "did:web:third-party.dataspaces.localhost:users:consumer-user"
TYPE = "OrganizationCredential"


async def _admitted(kind: str = "credential_type", value: str = TYPE) -> bool:
    return await _check_constraint(kind, value, SUBJECT, REGISTRY)


@pytest.mark.asyncio
@respx.mock
async def test_it_asks_the_narrow_check_not_the_roster():
    """`GET /admin/credentials` needs `identity-registry.admin`, which
    `clients.yaml` refuses a service client. The question is asked of
    `/credentials/check`, which the connector's own grant reaches."""
    route = respx.get(f"{REGISTRY}/credentials/check").mock(
        return_value=httpx.Response(
            200, json={"subject_did": SUBJECT, "credential_type": TYPE, "holds": True}
        )
    )
    roster = respx.get(f"{REGISTRY}/admin/credentials").mock(
        return_value=httpx.Response(403)
    )

    assert await _admitted() is True
    assert route.called
    assert not roster.called


@pytest.mark.asyncio
@respx.mock
async def test_the_credential_type_reaches_the_registry():
    """The old route accepts a `type` parameter and ignores it, so the answer
    covered every credential the subject holds. The type must be *applied*, and
    the only place that can apply it is the registry."""
    captured = {}

    def record(request):
        captured.update(dict(request.url.params))
        return httpx.Response(
            200, json={"subject_did": SUBJECT, "credential_type": TYPE, "holds": True}
        )

    respx.get(f"{REGISTRY}/credentials/check").mock(side_effect=record)
    await _admitted()
    assert captured == {"subject_did": SUBJECT, "type": TYPE}


@pytest.mark.asyncio
@respx.mock
async def test_a_negative_answer_does_not_admit():
    """The failure that a `revoked`-shaped read could not express.

    `CredentialSummary` carries `status`, never `revoked`, so
    `not item.get("revoked", False)` was `True` for every entry — a revoked
    credential admitted, and so did one of the wrong type.
    """
    respx.get(f"{REGISTRY}/credentials/check").mock(
        return_value=httpx.Response(
            200, json={"subject_did": SUBJECT, "credential_type": TYPE, "holds": False}
        )
    )
    assert await _admitted() is False


@pytest.mark.asyncio
@respx.mock
async def test_a_body_that_does_not_say_holds_does_not_admit():
    """A response shape we do not recognise is not a yes.

    This is the exact class of the original defect: reading a key that is not
    there and defaulting it in the admitting direction.
    """
    respx.get(f"{REGISTRY}/credentials/check").mock(
        return_value=httpx.Response(200, json={"credential_type": TYPE})
    )
    assert await _admitted() is False


@pytest.mark.asyncio
@respx.mock
async def test_a_refusal_does_not_admit():
    respx.get(f"{REGISTRY}/credentials/check").mock(return_value=httpx.Response(403))
    assert await _admitted() is False


@pytest.mark.asyncio
@respx.mock
async def test_an_unreachable_registry_does_not_admit():
    """An unverifiable credential claim admits nobody. Rulebook `CR-4`."""
    respx.get(f"{REGISTRY}/credentials/check").mock(
        side_effect=httpx.ConnectError("registry down")
    )
    assert await _admitted() is False


@pytest.mark.asyncio
@respx.mock
async def test_an_unknown_constraint_kind_admits_nobody():
    admitted = await _check_constraint("phase_of_the_moon", "waxing", SUBJECT, REGISTRY)
    assert admitted is False
