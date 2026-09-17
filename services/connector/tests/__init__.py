import base64
import json
import time
from urllib.parse import quote

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


def edc_v5_root() -> str:
    """This connector's own participant context path, as the client builds it."""
    from connector.config import get_settings

    settings = get_settings()
    return (
        f"{settings.edc_management_url.rstrip('/')}/"
        f"{settings.edc_management_api_version}/participants/"
        f"{quote(settings.participant_context_id, safe='')}"
    )


def attach_edc(app) -> None:
    """Give a test app the EDC client the lifespan would build (no auth)."""
    from ds_edc import EdcManagementClient

    from connector.config import get_settings

    settings = get_settings()
    app.state.edc = EdcManagementClient(
        settings.edc_management_url,
        settings.participant_context_id,
        api_version=settings.edc_management_api_version,
    )


def make_org_headers(
    context: str | None = None,
    scopes: tuple[str, ...] = (
        "management-api:catalog:read",
        "management-api:negotiations:write",
        "management-api:agreements:read",
        "management-api:transfers:write",
    ),
    alias: str = "example-org",
) -> dict:
    """An organisation client's bearer: `sub` = the participant context.

    What `svc-ds-connector-<alias>` mints once its `sub` mapper is in place. The
    default context is this test connector's own (`participant_context_id`).
    """
    from connector.config import get_settings

    token = pyjwt.encode(
        _claims(
            sub=context or get_settings().participant_context_id,
            azp=f"svc-ds-connector-{alias}",
            preferred_username=f"service-account-svc-ds-connector-{alias}",
            scope=" ".join(scopes),
            iss="http://keycloak.test/realms/dataspaces",
        ),
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
