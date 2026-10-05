from __future__ import annotations

import logging
from datetime import UTC, datetime

from ds_auth.fastapi import authenticate, get_oidc_config
from ds_auth.person_binding import realm_of
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import Credential, KeycloakMapping
from ...dependencies import (
    get_db,
    get_settings_dep,
    require_read_scope,
    require_resolve_scope,
)
from ...schemas.requests import UserResolveRequest
from ...schemas.responses import (
    SubjectIdentityResponse,
    UserCredentialResponse,
    UserResolveResponse,
)
from ...services.did import subject_id_of

router = APIRouter(prefix="/users", tags=["users"])

log = logging.getLogger(__name__)


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    """Whether a credential is past its expiry.

    ``DateTime(timezone=True)`` only round-trips tzinfo on PostgreSQL; SQLite
    hands back a naive value, so comparing it directly raises. Stored timestamps
    are UTC by convention, so a naive one is read as UTC — the same
    normalisation `connector/services/pending_sweep.py` does.
    """
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def _to_credential_response(credential: Credential) -> UserCredentialResponse:
    cred_json = credential.credential_json or {}
    subject = cred_json.get("credentialSubject") or {}
    proof = cred_json.get("proof") or {}
    return UserCredentialResponse(
        role=subject.get("role"),
        vc_jws=proof.get("jws"),
        credential_type=credential.credential_type,
        issued_at=credential.issued_at,
        expires_at=credential.expires_at,
    )


async def resolve_mapping(
    db: AsyncSession,
    *,
    realm: str | None = None,
    user_id: str | None = None,
    username: str | None = None,
    email: str | None = None,
) -> tuple[KeycloakMapping | None, str | None]:
    """Find a user's mapping by the cascade ``id > username > email``.

    Three identifiers, three different jobs, and only one of them means "the same
    human":

    * ``(realm, user_id)`` — the **continuity key**. Stable within a realm, and the
      only one an IdP does not let people change.
    * ``username`` — the **data-plane join**. The REC registry resolves a member by
      it, so it is load-bearing and mutable at the same time.
    * ``email`` — a **bootstrap seed**. It is the identifier that actually moves,
      and deriving a subject id from it is a convenience for a first-time user, not
      a statement about who someone is.

    Returns ``(mapping, conflict)``. ``conflict`` is set when a *weaker* identifier
    matched a row that already carries a **different** stronger one — the caller
    must not reconcile that, because two irreconcilable situations look identical
    from here: an IdP that deleted and re-created the account (same human, new
    ``user_id``) and a username or address **recycled to a different human**. The
    first should update the row; the second would hand one person's DID,
    credentials and consent history to somebody else. ds cannot tell them apart,
    and in a realm it does not administer it cannot ask.
    """
    if realm and user_id:
        result = await db.execute(
            select(KeycloakMapping).where(
                KeycloakMapping.keycloak_realm == realm,
                KeycloakMapping.keycloak_user_id == user_id,
            )
        )
        mapping = result.scalar_one_or_none()
        if mapping:
            return mapping, None

    for column, value in (
        (KeycloakMapping.username, username),
        (KeycloakMapping.email, email),
    ):
        if not value:
            continue
        result = await db.execute(
            select(KeycloakMapping).where(func.lower(column) == value.strip().lower())
        )
        # `.all()` rather than `scalar_one_or_none()`: a duplicate must be reported,
        # not raised as a 500 from deep inside the ORM.
        rows = result.scalars().all()
        if len(rows) > 1:
            return None, "ambiguous"
        if rows:
            mapping = rows[0]
            if (
                user_id
                and mapping.keycloak_user_id
                and mapping.keycloak_user_id != user_id
            ):
                return mapping, "conflict"
            return mapping, None

    return None, None


@router.post("/resolve", response_model=UserResolveResponse)
async def resolve_user(
    body: UserResolveRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_resolve_scope),
):
    """Resolve a user's DID and **every** credential they can present.

    The identifiers travel in the body, never in the URL: an email or a
    username in a query string is recorded by every access log, proxy and
    trace on the path. Cascade ``(realm, user_id)`` > ``username`` > ``email``
    (`resolve_mapping`).

    One human legitimately holds several roles, so this returns all of them and
    lets the caller select the credential the operation requires. See
    ``UserResolveResponse`` for why the singular fields remain.

    A person with no mapping is a **404**: the registry does not invent an
    identifier. A caller enrolling someone for the first time mints an opaque
    subject id itself (a random UUID is the simple compliant choice, `D-22c`)
    and passes it to ``POST /admin/credentials/data-subject``.

    ``subject_id`` is the person's identifier within their custodian's
    namespace, which is what ``POST /admin/credentials/data-subject`` takes;
    ``did`` is the field that carries the DID (ds#31).
    """
    return await _resolve(
        db,
        realm=body.realm,
        user_id=body.user_id,
        username=body.username,
        email=body.email,
    )


@router.get("/resolve", response_model=UserResolveResponse, deprecated=True)
async def resolve_user_by_query(
    response: Response,
    email: str | None = Query(None, description="User email address"),
    realm: str | None = Query(
        None, description="Keycloak realm — with user_id, the continuity key"
    ),
    user_id: str | None = Query(
        None, description="Keycloak user id — the only identifier that cannot change"
    ),
    username: str | None = Query(None, description="Keycloak preferred_username"),
    derive: bool = Query(
        False,
        deprecated=True,
        description=(
            "Removed. The registry no longer derives a subject id: with no "
            "mapping, `derive=true` answers 422. Accepted so existing callers "
            "sending `derive=false` keep working"
        ),
    ),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_resolve_scope),
):
    """**Deprecated** — use ``POST /users/resolve`` with a JSON body.

    The same lookup, with the identifiers in the query string, where every
    access log and proxy on the path records them. Kept for a compatibility
    window (``IDENTITY_REGISTRY_USERS_RESOLVE_GET``, ``…_UNTIL``): served in
    dev, and elsewhere until the window closes, then a **410**. Each call
    served logs a warning naming which identifiers were sent, never their
    values; a successful answer carries ``Deprecation`` and ``Sunset`` headers.
    """
    if not settings.users_resolve_get_allowed():
        raise HTTPException(
            status_code=410,
            detail=(
                "GET /users/resolve is withdrawn: an identifier in a URL is "
                "logged wherever the request goes. Send POST /users/resolve "
                "with a JSON body ({realm, user_id, username, email})."
            ),
        )
    sent = [
        name
        for name, value in (
            ("realm", realm),
            ("user_id", user_id),
            ("username", username),
            ("email", email),
        )
        if value
    ]
    log.warning(
        "deprecated GET /users/resolve served (identifiers: %s); move the caller "
        "to POST /users/resolve",
        ", ".join(sent) or "none",
    )
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = settings.users_resolve_get_until.isoformat()
    return await _resolve(
        db,
        realm=realm,
        user_id=user_id,
        username=username,
        email=email,
        derive=derive,
    )


async def _resolve(
    db: AsyncSession,
    *,
    realm: str | None,
    user_id: str | None,
    username: str | None,
    email: str | None,
    derive: bool = False,
) -> UserResolveResponse:
    """The lookup both forms of ``/users/resolve`` share.

    **``derive`` is deprecated** (GET only). It used to answer an unmapped person with
    ``email-`` and an HMAC of their email. That generator is removed: an
    identifier derived from the email ties the DID to an address that can
    change. ``derive=true`` with no mapping now answers **422** naming what to
    do instead, rather than a 404 a caller could read as "unknown, go ahead"
    without learning that the behaviour it relied on is gone. With a mapping,
    and with ``derive=false``, the parameter changes nothing. DIDs issued as
    ``…:users:email-<24hex>`` before the removal are stored ids like any other
    and resolve through their mapping; nothing re-derives them.

    ``subject_id`` is the person's identifier within their custodian's
    namespace, which is what ``POST /admin/credentials/data-subject`` takes;
    ``did`` is the field that carries the DID. The two used to be the same
    string when a mapping existed, which made the documented round trip —
    resolve, then issue with ``subject_id`` — mint a second identity for a
    person who already had one (ds#31).
    """
    if not any((email, username, (realm and user_id))):
        raise HTTPException(
            status_code=422,
            detail="Provide (realm, user_id), username, or email",
        )

    mapping, conflict = await resolve_mapping(
        db, realm=realm, user_id=user_id, username=username, email=email
    )
    if conflict:
        # Quarantine, not a guess. See `resolve_mapping` for why this cannot be
        # auto-reconciled.
        raise HTTPException(
            status_code=409,
            detail=(
                f"identifier {conflict}: the identifier given matches a mapping that "
                "carries a different Keycloak user id. This is either a re-created "
                "account or a recycled identifier, and they are indistinguishable "
                "from here — an operator must decide."
            ),
        )
    if not mapping:
        if derive:
            # Refused exactly where the removed generator used to answer, so a
            # caller that relied on it learns so here, not from a 404 that reads
            # as "unknown person, go ahead".
            raise HTTPException(
                status_code=422,
                detail=(
                    "derive=true is no longer supported: the registry does not "
                    "derive subject ids. No mapping exists for this user; mint an "
                    "opaque subject id (for example a random UUID), pass it to "
                    "POST /admin/credentials/data-subject, and record the mapping "
                    "(POST /admin/keycloak/sync)"
                ),
            )
        raise HTTPException(status_code=404, detail="No mapping found for this user")

    cred_result = await db.execute(
        select(Credential)
        .where(
            Credential.subject_did == mapping.did,
            Credential.status == "active",
        )
        .order_by(Credential.issued_at.desc())
    )

    # An expired credential is not presentable — the verifier rejects it — so
    # offering it as a candidate only produces a failure the caller cannot
    # explain. `status == "active"` alone does not imply unexpired.
    now = datetime.now(UTC)
    credentials = [
        _to_credential_response(c)
        for c in cred_result.scalars().all()
        if not _is_expired(c.expires_at, now)
    ]
    presentable = [c for c in credentials if c.vc_jws]
    newest = presentable[0] if presentable else None

    # **`subject_id` is the id inside the DID** — the person's identifier
    # *within their custodian's namespace*, which is what `subject_did_for`
    # takes. It used to be
    # `mapping.subject_id`, and both write paths store the full DID there, so
    # this field answered with a DID when a mapping existed and a short id when
    # it did not. A caller following the docstring — resolve, then reuse
    # `subject_id` for issuance — minted a second identity for a person who
    # already had one (ds#31). `did` is the field that carries the DID.
    #
    # Derived at the point of reading rather than migrated: the column is the
    # lookup key of `GET /admin/keycloak/mapping?subject_id=…`, whose callers
    # pass a DID. The fallback keeps a mapping whose `did` is not a person's DID
    # at all — nothing writes one, but this route should not reshape it into
    # `None` if something ever does.
    return UserResolveResponse(
        did=mapping.did,
        subject_id=subject_id_of(mapping.did) or mapping.subject_id,
        roles=[c.role for c in credentials if c.role],
        credentials=credentials,
        role=newest.role if newest else None,
        vc_jws=newest.vc_jws if newest else None,
    )


@router.get("/{subject_did:path}/credentials", response_model=UserResolveResponse)
async def credentials_held_for(
    subject_did: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    _claims: dict = Depends(require_resolve_scope),
):
    """What **this instance holds** for a person — `DID-11` step 2.

    The holder-side half of `/users/resolve`, and the split is the point:

    * *who is this person* — a Keycloak identity, a subject id, a DID — is
      **registry** data and stays at the trust anchor;
    * *what credentials do they hold* is **custody**, and after `D-49`/`D-50`
      that lives with the organisation that onboarded them.

    So a REC-side application asks its own instance this, rather than asking the
    anchor for credentials the anchor happens to have issued. The anchor keeps
    its issuance record — the issuer knows what it attested — but a participant
    reading credentials from the issuer is a participant that does not really
    hold anything, which is the shape `DID-05` removed for participants and this
    removes for the people they hold credentials for.

    Takes the DID rather than an email because this instance has no Keycloak
    mappings: those are registry data. Two calls, two questions, two owners.
    """
    # Bound, not re-derived. The guard below already establishes that this is a
    # subject DID; calling `subject_id_of` again at the response left mypy with
    # `str | None` for a value this function has refused to proceed without.
    subject_id = subject_id_of(subject_did)
    if subject_id is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "not a subject DID — a person's identifier is "
                "did:web:<participant>:users:<id> (D-50)"
            ),
        )

    # **The namespace is deliberately not the test.** It was, briefly, and it was
    # wrong: a person is *named* by the organisation that onboarded them and can
    # hold credentials from a relationship with another — the dual-role case this
    # fixture has. Refusing on namespace would have hidden a credential this
    # instance legitimately holds.
    #
    # What bounds the answer is what is *in this database*: an instance holds
    # what was delivered to it and answers with that, and for a person it holds
    # nothing about the answer is empty.

    rows = (
        (
            await db.execute(
                select(Credential)
                .where(
                    Credential.subject_did == subject_did, Credential.status == "active"
                )
                .order_by(Credential.issued_at.desc())
            )
        )
        .scalars()
        .all()
    )

    now = datetime.now(UTC)
    credentials = [
        _to_credential_response(c) for c in rows if not _is_expired(c.expires_at, now)
    ]
    presentable = [c for c in credentials if c.vc_jws]
    newest = presentable[0] if presentable else None
    return UserResolveResponse(
        did=subject_did,
        subject_id=subject_id,
        roles=[c.role for c in credentials if c.role],
        credentials=credentials,
        role=newest.role if newest else None,
        vc_jws=newest.vc_jws if newest else None,
    )


class SubjectIdentitiesRequest(BaseModel):
    """DIDs to translate into the identifiers other systems key on."""

    dids: list[str]


@router.post("/identities", response_model=list[SubjectIdentityResponse])
async def resolve_subject_identities(
    body: SubjectIdentitiesRequest,
    db: AsyncSession = Depends(get_db),
    _claims: dict = Depends(require_read_scope),
):
    """Translate subject DIDs into the username a non-dataspace system keys on.

    A dataspace decision names people by DID. The systems that hold their data
    do not: the REC registry resolves a member by Keycloak's
    ``preferred_username``. Something has to bridge the two, and it has to be
    the registry that already stores the link — deriving it anywhere else means
    guessing, and a wrong guess reads another person's data.

    **Batched on purpose.** The caller is resolving the whole consented-subject
    set for one query; one request per subject would put a fan-out on the hot
    path of every data-plane read.

    A DID with no mapping is **omitted** rather than returned empty, and no
    error is raised: the caller must not be able to tell "unknown subject" from
    "subject with no username", or this becomes a directory of who exists.
    """
    if not body.dids:
        return []
    result = await db.execute(
        select(KeycloakMapping).where(KeycloakMapping.did.in_(body.dids))
    )
    identities = []
    for mapping in result.scalars().all():
        # `email` is the documented fallback: this realm sets username = email,
        # and rows predating the column carry only the email. Nothing further is
        # inferred.
        username = mapping.username or mapping.email
        if not username:
            continue
        identities.append(SubjectIdentityResponse(did=mapping.did, username=username))
    return identities


class OwnSubjectResponse(BaseModel):
    """The subject DID the presenter's own login is bound to."""

    did: str


@router.get("/me", response_model=OwnSubjectResponse)
async def own_subject(request: Request, db: AsyncSession = Depends(get_db)):
    """Which subject is the person presenting this login token?

    The question a person route asks before acting on a user credential
    (`ds_auth.person_binding`): the credential says *which* subject, the login
    token says *who logged in*, and only this registry stores the link between
    them — the `keycloak_mappings` row, unique per (realm, Keycloak user id),
    written when the person was onboarded.

    **Asked with the person's own token, forwarded by the service that received
    it** — not with a service token. So a service can learn a person's DID only
    while it holds that person's login, and this route is no directory: a
    service token is refused, and a login with no mapping is a 404.

    **Keyed on the Keycloak user id, never the email or username.** Both of
    those move; the user id is the one identifier the IdP does not let people
    change — `resolve_mapping` calls it the continuity key. The realm is the one
    this registry's issuer names, which the token's `iss` was just verified
    against.
    """
    principal = await authenticate(request, get_oidc_config(request))
    if principal.is_service:
        raise HTTPException(
            status_code=403,
            detail="This route answers a person about their own login; a service "
            "token names no person",
        )
    config = get_oidc_config(request)
    realm = realm_of(config.issuer_url) or realm_of(
        str(principal.claims.get("iss") or "")
    )
    if not realm or not principal.subject:
        raise HTTPException(status_code=401, detail="The token names no realm and user")
    result = await db.execute(
        select(KeycloakMapping.did).where(
            KeycloakMapping.keycloak_realm == realm,
            KeycloakMapping.keycloak_user_id == principal.subject,
        )
    )
    did = result.scalar_one_or_none()
    if did is None:
        raise HTTPException(
            status_code=404, detail="This login is bound to no dataspace subject"
        )
    return OwnSubjectResponse(did=did)
