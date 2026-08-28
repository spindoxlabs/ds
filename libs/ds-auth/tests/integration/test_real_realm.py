"""`ds_auth` verifies tokens the realm actually issues, carrying the scopes
`clients.yaml` actually declares.

Two claims, and the unit suite can make neither:

1. **The real verifier accepts a real token.** `test_verify.py` signs its own,
   so the RS256 / published-`kid` / list-valued-`aud` shape Keycloak produces has
   never been through `verify_token`.
2. **The realm grants what the file says.** `test_vocabulary.py` compares
   `clients.yaml` with `ds_auth.bundles` — declaration against declaration. The
   step that applies them is `celine-policies keycloak sync`, and its result was
   checked by nothing.
"""
from __future__ import annotations

import base64
import json

import pytest
from conftest import ISSUER, declared_clients, fetch_token

from ds_auth import OidcConfig, TokenInvalid, verify_token
from ds_auth.errors import AuthError

pytestmark = pytest.mark.integration

CLIENTS = declared_clients()
CLIENT_IDS = [c["client_id"] for c in CLIENTS]


def _payload(token: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "==="))


def _scopes(token: str) -> set[str]:
    return set(str(_payload(token).get("scope", "")).split())


# ── The realm grants what ds declares ────────────────────────────────────────


@pytest.mark.parametrize("client", CLIENTS, ids=CLIENT_IDS)
def test_the_realm_grants_every_scope_the_file_declares(client, keycloak_is_up):
    """`clients.yaml`'s `default_scopes` ⊆ the token's `scope` claim.

    Subset, not equality: a deployment's domain overlay
    (`clients.<domain>.yaml`) is passed to the same sync with `--overlay` and
    legitimately adds more — `svc-ds-e2e` carries `rec-registry.admin` in dev
    from exactly that. Granting *more* than ds asks for is the deployment's business.
    Granting less is the defect, and it surfaces as a 403 in a service whose
    own tests all pass.
    """
    granted = _scopes(fetch_token(client["client_id"]))
    missing = set(client["default_scopes"]) - granted

    assert not missing, (
        f"{client['client_id']} is missing scopes clients.yaml declares:\n"
        + "\n".join(f"  - {s}" for s in sorted(missing))
        + "\n\nThe declaration and the realm have diverged — the sync was not "
        "run, or ran without the file that declares this grant. Re-run it with "
        "the core and every overlay: see `keycloak-sync` in docker-compose.yml."
    )


# ── The real verifier accepts a real token ───────────────────────────────────


@pytest.fixture(scope="session")
def e2e_token(keycloak_is_up) -> str:
    """The harness client's token — the one with the widest audience list."""
    return fetch_token("svc-ds-e2e")


def test_a_real_keycloak_token_passes_the_real_verifier(e2e_token):
    """The whole point: no self-signed fixture, no stubbed JWKS.

    The signing key is fetched from the realm's published JWKS by `kid`, and
    every check `verify_token` makes runs against a token this realm minted.
    """
    audience = _payload(e2e_token)["aud"][0]
    claims = verify_token(e2e_token, OidcConfig(issuer_url=ISSUER, audience=audience))
    assert claims["azp"] == "svc-ds-e2e"
    assert claims["iss"] == ISSUER


def test_the_token_is_signed_with_an_algorithm_the_verifier_allows(e2e_token):
    """A realm that switched signing algorithm would fail every service at once.

    `OidcConfig.algorithms` is `("RS256", "ES256")`, and a token signed with
    anything else is refused by the *library* rather than by the realm — which
    reads as "our tokens stopped working" and not as a realm setting. Asserted
    here because only a real realm has an opinion about it.
    """
    header = json.loads(base64.urlsafe_b64decode(e2e_token.split(".")[0] + "==="))
    assert header["alg"] in OidcConfig().algorithms
    assert header.get("kid"), "no kid: the verifier cannot select a signing key"


def test_a_list_valued_audience_is_accepted_for_each_member(e2e_token):
    """Keycloak's `aud` is a **list**, and every member must verify.

    The unit fixtures use a single string. A verifier that happened to compare
    `aud == audience` rather than membership would pass every one of them and
    fail against every real token — for all services at once, which is the kind
    of break that looks like Keycloak going down.
    """
    audiences = _payload(e2e_token)["aud"]
    assert isinstance(audiences, list) and len(audiences) > 1, (
        "expected a multi-audience service token; the audience mappers "
        "`clients.yaml` generates may have stopped being applied"
    )
    for audience in audiences:
        claims = verify_token(
            e2e_token, OidcConfig(issuer_url=ISSUER, audience=audience)
        )
        assert claims["azp"] == "svc-ds-e2e"


# ── …and refuses, against the same real token ────────────────────────────────


def test_an_audience_the_token_does_not_carry_is_refused(e2e_token):
    """Fail-closed, proven on a genuine token rather than a crafted one.

    `AUTH-01` is the reminder for why this belongs here: the `insecure_dev` path
    accepted expired tokens for as long as it did while its unit tests passed.
    """
    with pytest.raises((TokenInvalid, AuthError)):
        verify_token(
            e2e_token,
            OidcConfig(issuer_url=ISSUER, audience="svc-not-a-real-client"),
        )


def test_a_foreign_issuer_is_refused(e2e_token):
    """The realm URL is half the trust decision; a token from elsewhere is not
    ours even if its signature checks out somewhere."""
    with pytest.raises((TokenInvalid, AuthError)):
        verify_token(
            e2e_token,
            OidcConfig(
                issuer_url="http://keycloak.dataspaces.localhost/realms/other",
                audience=_payload(e2e_token)["aud"][0],
            ),
        )
