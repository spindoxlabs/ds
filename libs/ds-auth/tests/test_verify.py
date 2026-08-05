import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

import ds_auth.jwt as ds_jwt
from ds_auth import OidcConfig, TokenInvalid, verify_token
from ds_auth.errors import AuthConfigError

ISSUER = "http://keycloak:9080/realms/dataspaces"
AUD = "svc-ds-connector"


@pytest.fixture
def ec_key():
    return ec.generate_private_key(ec.SECP256R1())


def _sign(key, claims, alg="ES256"):
    return pyjwt.encode(claims, key, algorithm=alg)


def _base_claims(**over):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUD,
        "sub": "svc",
        "iat": now,
        "exp": now + 300,
        "scope": "connector.admin",
    }
    claims.update(over)
    return claims


@pytest.fixture
def signed_config(monkeypatch, ec_key):
    class _StubKey:
        key = ec_key.public_key()

    class _StubClient:
        def get_signing_key_from_jwt(self, token):
            return _StubKey()

    monkeypatch.setattr(ds_jwt, "_jwks_client", lambda uri: _StubClient())
    return OidcConfig(issuer_url=ISSUER, audience=AUD)


def test_verifies_valid_token(signed_config, ec_key):
    token = _sign(ec_key, _base_claims())
    claims = verify_token(token, signed_config)
    assert claims["scope"] == "connector.admin"


def test_rejects_bad_audience(signed_config, ec_key):
    token = _sign(ec_key, _base_claims(aud="someone-else"))
    with pytest.raises(TokenInvalid):
        verify_token(token, signed_config)


def test_rejects_bad_issuer(signed_config, ec_key):
    token = _sign(ec_key, _base_claims(iss="http://evil/realms/x"))
    with pytest.raises(TokenInvalid):
        verify_token(token, signed_config)


def test_rejects_expired(signed_config, ec_key):
    token = _sign(ec_key, _base_claims(exp=int(time.time()) - 3600))
    with pytest.raises(TokenInvalid):
        verify_token(token, signed_config)


def test_fail_closed_without_issuer():
    cfg = OidcConfig(issuer_url=None, insecure_dev=False)
    token = _sign(
        ec.generate_private_key(ec.SECP256R1()), _base_claims(), alg="ES256"
    )
    with pytest.raises(AuthConfigError):
        verify_token(token, cfg)


def test_insecure_dev_accepts_unverified():
    cfg = OidcConfig(issuer_url=None, insecure_dev=True)
    # Signed with a throwaway key the config knows nothing about.
    token = _sign(ec.generate_private_key(ec.SECP256R1()), _base_claims())
    claims = verify_token(token, cfg)
    assert claims["scope"] == "connector.admin"


# `insecure_dev` skips the signature and the audience — the two things a service
# with no issuer cannot check. It does **not** skip the claim-set checks, which
# need no key. PyJWT turns those off along with the signature unless each is
# re-enabled by name, so these three tests are the whole of what stops that
# regressing.


def test_insecure_dev_rejects_expired():
    cfg = OidcConfig(issuer_url=None, insecure_dev=True)
    token = _sign(
        ec.generate_private_key(ec.SECP256R1()),
        _base_claims(exp=int(time.time()) - 3600),
    )
    with pytest.raises(TokenInvalid):
        verify_token(token, cfg)


def test_insecure_dev_rejects_not_yet_valid():
    cfg = OidcConfig(issuer_url=None, insecure_dev=True)
    token = _sign(
        ec.generate_private_key(ec.SECP256R1()),
        _base_claims(nbf=int(time.time()) + 3600),
    )
    with pytest.raises(TokenInvalid):
        verify_token(token, cfg)


def test_insecure_dev_requires_exp():
    """A token with no `exp` cannot expire, so accepting one re-opens the hole."""
    cfg = OidcConfig(issuer_url=None, insecure_dev=True)
    claims = _base_claims()
    del claims["exp"]
    token = _sign(ec.generate_private_key(ec.SECP256R1()), claims)
    with pytest.raises(TokenInvalid):
        verify_token(token, cfg)
