"""Test-token minting.

The key is a per-run random one, not a literal. It is deliberately *irrelevant*:
the suite runs with no issuer configured and `PROVENANCE_OIDC_INSECURE_DEV`
defaulted true, so `ds_auth.verify_token` decodes without checking the signature.
Two consequences worth stating rather than leaving to be discovered:

- **A green run here proves authorization, not authentication.** These tests pin
  which scope reaches which route. That signatures are verified once an issuer
  *is* configured is `libs/ds-auth`'s own suite; the posture this suite runs
  under is asserted in `test_lifespan.py`.
- A shared literal (`"secret"`) invited exactly the opposite reading, and warned
  on every call besides — a 6-byte HMAC key is below the RFC 7518 minimum.
"""
import secrets

import jwt as pyjwt

#: Random per run, so nothing can come to depend on the value.
_TEST_SIGNING_KEY = secrets.token_hex(32)


def make_headers(scope: str = "provenance.write provenance.read") -> dict:
    token = pyjwt.encode(
        {
            "scope": scope,
            "sub": "test",
            "preferred_username": "service-account-svc-ds-provenance",
        },
        _TEST_SIGNING_KEY,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
