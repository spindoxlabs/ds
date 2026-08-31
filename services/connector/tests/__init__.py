import base64
import json
import time

import jwt as pyjwt


def _claims(**over: object) -> dict:
    """Base claims for a minted test token.

    **Every token carries `exp`.** Keycloak has never issued one without it, and
    since `ds_auth.verify_token` checks expiry even on the `insecure_dev` path —
    signature and audience are the only things it skips — a fixture without `exp`
    is both unrealistic and rejected. It used to be accepted, which is what let
    an expired token through a dev deployment.
    """
    now = int(time.time())
    claims: dict = {"iat": now, "exp": now + 300}
    claims.update(over)
    return claims


def make_headers(scope: str = "connector.admin") -> dict:
    """A service-account bearer (scope-based authority).

    ``preferred_username=service-account-*`` is what marks a Keycloak
    client-credentials token as a service account, so ds-auth authorizes it on
    its ``scope`` claim (vs a user token, which authorizes on groups).
    """
    token = pyjwt.encode(
        _claims(
            scope=scope,
            sub="test",
            preferred_username="service-account-svc-ds-test",
        ),
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def make_vc_headers(
    subject_did: str = "did:web:rec.dataspaces.localhost:users:sub-001",
    role: str = "DataSubject",
    linked_participant: str = "did:web:rec.dataspaces.localhost",
) -> dict:
    """VC-JWT headers for the ``/consent/*`` and ``/consumer/*`` surfaces.

    Those routes authenticate on ``X-Subject-Id`` + ``X-User-VC`` rather than
    ``require_permission`` — a distinct mechanism, and using the wrong one is
    the most common security mistake in this repo. The signature is not
    verified here because the test settings leave the trust-anchor key unset
    (``CONNECTOR_VC_INSECURE_DEV`` default), but every other claim is checked,
    so the token still has to be well-formed.

    ``linked_participant`` has to match whichever participant the route checks
    against: the ``/consent/*`` routes are the provider's, while ``/consumer/*``
    checks ``CONNECTOR_CONSUMER_PARTICIPANT_DID``. Defaulting it to the provider
    and forgetting to override it produces a 403 that looks like a scope problem.
    """
    header = _b64url(json.dumps({"alg": "ES256", "typ": "JWT"}))
    payload = _b64url(
        json.dumps(
            {
                "iss": "did:web:trust-anchor.dataspaces.localhost",
                "sub": subject_did,
                "vc": {
                    "issuer": "did:web:trust-anchor.dataspaces.localhost",
                    "credentialSubject": {
                        "id": subject_did,
                        "role": role,
                        "linkedParticipant": linked_participant,
                    },
                },
            }
        )
    )
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
        _claims(
            sub="user-test",
            email="user@example.test",
            groups=list(groups or []),
        ),
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
