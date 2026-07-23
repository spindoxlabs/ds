import base64
import json

import jwt as pyjwt


def make_headers(scope: str = "connector.admin") -> dict:
    """A service-account bearer (scope-based authority).

    ``preferred_username=service-account-*`` is what marks a Keycloak
    client-credentials token as a service account, so ds-auth authorizes it on
    its ``scope`` claim (vs a user token, which authorizes on groups).
    """
    token = pyjwt.encode(
        {
            "scope": scope,
            "sub": "test",
            "preferred_username": "service-account-svc-ds-test",
        },
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def make_vc_headers(
    subject_did: str = "did:web:users.dataspaces.localhost:sub-001",
    role: str = "DataSubject",
) -> dict:
    """VC-JWT headers for the ``/consent/*`` and ``/consumer/*`` surfaces.

    Those routes authenticate on ``X-Subject-Id`` + ``X-User-VC`` rather than
    ``require_permission`` — a distinct mechanism, and using the wrong one is
    the most common security mistake in this repo. The signature is not
    verified here because the test settings leave the trust-anchor key unset
    (``CONNECTOR_VC_INSECURE_DEV`` default), but every other claim is checked,
    so the token still has to be well-formed.
    """
    header = _b64url(json.dumps({"alg": "ES256", "typ": "JWT"}))
    payload = _b64url(json.dumps({
        "iss": "did:web:trust-anchor.dataspaces.localhost",
        "sub": subject_did,
        "vc": {
            "issuer": "did:web:trust-anchor.dataspaces.localhost",
            "credentialSubject": {
                "id": subject_did,
                "role": role,
                "linkedParticipant": "did:web:provider.dataspaces.localhost",
            },
        },
    }))
    return {
        "X-Subject-Id": subject_did,
        "X-User-VC": f"{header}.{payload}.{_b64url('unverified-in-dev')}",
    }


def _b64url(value: str | bytes) -> str:
    raw = value.encode() if isinstance(value, str) else value
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_user_headers(groups: list[str] | None = None) -> dict:
    """A user bearer (group-based authority)."""
    token = pyjwt.encode(
        {
            "sub": "user-test",
            "email": "user@example.test",
            "groups": list(groups or []),
        },
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
