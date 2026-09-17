"""An organisation acting as itself is classified as such, and only by its client.

An organisation's client (`svc-ds-connector-<alias>`) carries the participant
context as `sub`. A caller binds such a token to its own participant by comparing
`organisation_context` with its own context id (plan
`the-management-api-is-v3-behind-one-key`, decisions 1-2).
"""

from __future__ import annotations

import time

import pytest

from ds_auth import Principal

DID = "did:web:rec.example.org"


def _claims(**over) -> dict:
    now = int(time.time())
    claims = {
        "iat": now,
        "exp": now + 300,
        "sub": DID,
        "azp": "svc-ds-connector-example-rec",
        "preferred_username": "service-account-svc-ds-connector-example-rec",
        "scope": "management-api:negotiations:write management-api:catalog:read",
    }
    claims.update(over)
    return claims


def test_an_organisation_client_token_is_an_organisation_actor():
    principal = Principal.from_claims(_claims())
    assert principal.is_service
    assert principal.is_organisation
    assert principal.organisation_context == DID
    assert principal.actor == f"org:{DID}"
    assert principal.client_id == "svc-ds-connector-example-rec"


@pytest.mark.parametrize(
    "over",
    [
        # Another service client, even one whose `sub` looks like a DID.
        {"azp": "svc-ds-e2e", "preferred_username": "service-account-svc-ds-e2e"},
        # A person, whatever their client.
        {"preferred_username": "someone@example.test", "email": "someone@example.test"},
        # No client at all.
        {"azp": None, "client_id": None},
    ],
)
def test_nothing_else_is(over):
    claims = {k: v for k, v in _claims(**over).items() if v is not None}
    principal = Principal.from_claims(claims)
    assert not principal.is_organisation
    assert principal.organisation_context is None
    assert principal.actor == principal.subject


def test_the_organisation_actor_holds_edc_scopes_by_edc_s_grammar():
    principal = Principal.from_claims(_claims())
    assert principal.grants_management_scope("management-api:negotiations:read")
    assert principal.grants_management_scope("management-api:catalog:read")
    assert not principal.grants_management_scope("management-api:transfers:write")


def test_a_person_never_holds_an_edc_scope():
    """A user token's `scope` claim is not authority (`is_service_account`)."""
    principal = Principal.from_claims(
        _claims(
            azp="oauth2_proxy",
            preferred_username="someone@example.test",
            email="someone@example.test",
        )
    )
    assert not principal.is_service
    assert not principal.grants_management_scope("management-api:catalog:read")


def test_an_edc_scope_is_not_a_ds_permission():
    """`management-api:*` never satisfies a ds `service.resource.action`."""
    principal = Principal.from_claims(_claims(scope="management-api:admin"))
    assert not principal.grants("connector.consumer.read")
    assert not principal.grants("connector.admin")
