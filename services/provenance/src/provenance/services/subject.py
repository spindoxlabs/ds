"""Data-subject identity for the subject-facing provenance view.

Provenance has two authentication models and they must not be conflated:

- everything else authorizes on a **scope** (`provenance.read` / `.write`),
  granted to an operator or a service;
- ``GET /prov/my/events`` authenticates a **person** with a verifiable
  credential, exactly as the connector's ``/consent/my/*`` routes do.

Both services verify the *same* credential the subject presents, so they share
one implementation (``ds_auth.user_credentials``). Duplicating that verification
per service is how two services end up disagreeing about who someone is.
"""

from __future__ import annotations

from ds_auth.fastapi import get_oidc_config
from ds_auth.person_binding import bind_login_token, person_token_required
from ds_auth.user_credentials import verify_user_vc_jwt
from fastapi import Request

from ..config import Settings


async def verified_subject_id(
    request: Request,
    x_user_vc: str | None,
    x_subject_id: str | None,
    settings: Settings,
) -> str:
    """The subject DID proven by the presented credential.

    Returns the DID from the *credential*, never the header alone: the header says
    who the caller claims to be, the credential is what makes it true. Callers
    filter on the result, so a subject cannot read another subject's history by
    changing a parameter.

    Raises ``HTTPException`` (401/403) when the credential is missing, malformed,
    unsigned by the trust anchor, revoked, or does not name the claimed subject —
    and, outside dev, when the request does not carry the person's own login
    token bound to that subject (R3, `ds_auth.person_binding`): the credential
    alone is a bearer credential any service that reads it may present.
    """
    credential = verify_user_vc_jwt(
        x_user_vc,
        x_subject_id,
        settings.trust_anchor_did,
        {"DataSubject", "ConsumerUser"},
        trust_list_url=settings.trust_list_url,
        did_web_use_https=settings.did_web_use_https,
        did_web_allowance=settings.did_web_allowance,
        credential_status_path=settings.credential_status_path,
        credential_status_url=settings.credential_status_url,
        insecure_dev=settings.vc_insecure_dev,
        status_cache_ttl_seconds=settings.credential_status_cache_seconds,
    )
    await bind_login_token(
        request,
        get_oidc_config(request),
        credential.subject_id,
        lookup=getattr(request.app.state, "login_binding", None),
        required=person_token_required(settings.person_token_required),
    )
    return credential.subject_id
