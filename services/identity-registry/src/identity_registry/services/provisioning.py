"""The connection bundle a promoted organisation needs to run its own ds instance.

Everything an operator would otherwise assemble by hand from four config files and
a database: who the participant is, how it authenticates to the STS, where the
trust anchor and credential service live, who it can talk to, and — because a
third-party connector authenticates service-to-service against *our* realm — its
Keycloak client credentials.

**It carries secrets, so it is returned once per call and the STS secret is rotated
each time.** The registry stores only a hash and physically cannot re-show one;
making the call rotate is the honest reading of "download it again", and it means a
leaked bundle can be invalidated by issuing another.

The renderers live here rather than in the API so `ir-cli` and the HTTP endpoint
emit byte-identical output — two implementations of a config template is how a
support call becomes "but mine says something different".
"""
from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import Owner, Participant
from .crypto import hash_sts_secret

# The grants a third-party connector needs against this dataspace. Deliberately
# the same set `svc-ds-connector` holds in `services/keycloak/clients.yaml` — a
# participant's connector is not a more privileged thing than ours.
#
# This is a **copy**, and it cannot be anything else at runtime: `clients.yaml`
# is not in the image (the Dockerfile ships `src/` and `alembic/` only), and
# this list is read by the HTTP promotion path inside a container. So the
# authority file cannot be consulted here — but the copy is pinned to it by
# `tests/test_provisioning_scopes.py`, which fails on any divergence.
#
# It had already drifted once, silently and in the direction that matters: the
# connector pass added `identity-registry.credentials.read` to
# `svc-ds-connector` (a sharing offer may admit by credential type, and
# `circle.py` reads it), and this list was not updated. Every third-party
# connector provisioned in between got a client whose credential check 403s.
CONNECTOR_SCOPES = [
    "identity-registry.read",
    "identity-registry.membership.read",
    "identity-registry.credentials.read",
    "provenance.write",
    "connector.consent.read",
]

# The services a third-party connector's token must be accepted by. Every ds
# service verifies `aud`, so a client created without these mappers holds a
# token that is refused everywhere it is presented — it authenticates and then
# fails at each call, which reads like a permission problem and is not one.
# Same source and same pinning as the scopes above.
CONNECTOR_AUDIENCES = [
    "svc-ds-identity-registry",
    "svc-ds-provenance",
    # The counterparty's connector — the audience of GET /consent/pending.
    "svc-ds-connector",
]


class ProvisioningError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def client_id_for(alias: str) -> str:
    return f"svc-ds-connector-{alias}"


async def build_bundle(
    db: AsyncSession,
    settings: Settings,
    owner: Owner,
    *,
    keycloak_client_id: str | None = None,
    keycloak_client_secret: str | None = None,
) -> dict[str, Any]:
    """Assemble the bundle and rotate the participant's STS secret.

    Refuses unless the organisation is actually a participant: a bundle for
    something that cannot be negotiated with is a support ticket waiting to happen.
    """
    if not owner.did:
        raise ProvisioningError(f"Owner {owner.id!r} has no DID", 422)

    result = await db.execute(select(Participant).where(Participant.did == owner.did))
    participant = result.scalar_one_or_none()
    if participant is None:
        raise ProvisioningError(
            f"Owner {owner.id!r} is not a registered participant — promote it first",
            409,
        )

    # Rotating here is what makes the secret safe to hand over: whatever was issued
    # before stops working, so an old bundle in an inbox is inert.
    sts_secret = secrets.token_urlsafe(32)
    participant.sts_client_secret = hash_sts_secret(sts_secret)

    ir = settings.identity_registry_public_url or f"https://{settings.trust_anchor_domain}"
    trust_anchor_did = f"did:web:{settings.trust_anchor_domain}"

    counterparties = await db.execute(
        select(Participant).where(
            Participant.did != owner.did,
            Participant.active.is_(True),
        )
    )

    bundle: dict[str, Any] = {
        "participant": {
            "did": owner.did,
            "alias": owner.id,
            "roles": participant.roles,
            "allowed_scopes": participant.allowed_scopes,
            "dsp_address": participant.dsp_address,
        },
        "identity": {
            "identity_registry_url": ir,
            "did_document_url": f"{ir}/dids/{owner.did}/did.json",
            "credential_service_url": f"{ir}/credentials/{owner.did}",
            "sts_token_url": f"{ir}/sts/{owner.did}/token",
            "sts_client_id": owner.did,
            # Shown once. The registry keeps only the hash.
            "sts_client_secret": sts_secret,
        },
        "trust": {
            "trust_anchor_did": trust_anchor_did,
            "trusted_issuers": [trust_anchor_did],
            "credential_status_url": f"{ir}/status/1",
        },
        "counterparties": [
            {"did": p.did, "dsp_address": p.dsp_address, "roles": p.roles}
            for p in counterparties.scalars().all()
        ],
    }

    if keycloak_client_id:
        bundle["keycloak"] = {
            "issuer_url": settings.keycloak_issuer_url,
            "client_id": keycloak_client_id,
            "client_secret": keycloak_client_secret,
            "scopes": CONNECTOR_SCOPES,
        }

    return bundle


# ── Renderers ────────────────────────────────────────────────────────────────
#
# One implementation, used by both the API and `ir-cli org bundle`.


def render_env(bundle: dict[str, Any]) -> str:
    """A `.env` fragment for the third party's ds deployment."""
    p, i, t = bundle["participant"], bundle["identity"], bundle["trust"]
    kc = bundle.get("keycloak") or {}
    provider = next(
        (c for c in bundle["counterparties"] if "provider" in (c.get("roles") or [])),
        None,
    )

    lines = [
        "# Generated by ir-cli / the identity registry. Contains secrets —",
        "# store it the way you store any other credential file.",
        "",
        f"CONNECTOR_PARTICIPANT_DID={p['did']}",
        f"CONNECTOR_PARTICIPANT_ID={p['alias']}",
        f"CONNECTOR_IDENTITY_REGISTRY_URL={i['identity_registry_url']}",
        "",
        "# STS — rotated when this bundle was generated; any previous value is dead.",
        f"EDC_IAM_STS_OAUTH_TOKEN_URL={i['sts_token_url']}",
        f"EDC_IAM_STS_OAUTH_CLIENT_ID={i['sts_client_id']}",
        f"EDC_IAM_STS_OAUTH_CLIENT_SECRET={i['sts_client_secret']}",
        "",
        f"IDENTITY_REGISTRY_TRUST_ANCHOR_DID={t['trust_anchor_did']}",
    ]
    if provider:
        lines += [
            "",
            "# The provider this deployment negotiates with by default.",
            f"CONSUMER_DEFAULT_ASSIGNER={provider['did']}",
            f"CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS={provider['dsp_address']}",
        ]
    if kc:
        lines += [
            "",
            "# Service-to-service credentials in the dataspace realm.",
            f"CONNECTOR_KEYCLOAK_TOKEN_URL={kc['issuer_url']}/protocol/openid-connect/token",
            f"CONNECTOR_SERVICE_CLIENT_ID={kc['client_id']}",
            f"CONNECTOR_SERVICE_CLIENT_SECRET={kc['client_secret']}",
        ]
    return "\n".join(lines) + "\n"


def render_properties(bundle: dict[str, Any]) -> str:
    """EDC `.properties` for the third party's connector.

    Secrets are **not** written here: `FsConfigurationExtension` does a plain
    `Properties.load()` with no interpolation, and EDC reads the environment as
    config anyway — so a secret belongs in the env, not in a file that tends to be
    committed.
    """
    p, i, t = bundle["participant"], bundle["identity"], bundle["trust"]
    return "\n".join(
        [
            "# Generated by ir-cli / the identity registry.",
            "# Secrets are supplied as environment variables — see the .env fragment.",
            "",
            f"edc.participant.id={p['did']}",
            f"edc.iam.issuer.id={p['did']}",
            f"edc.iam.sts.oauth.token.url={i['sts_token_url']}",
            f"edc.iam.sts.oauth.client.id={i['sts_client_id']}",
            "edc.iam.sts.oauth.client.secret.alias=sts-client-secret",
            f"edc.iam.trusted-issuer.0.id={t['trust_anchor_did']}",
            f"edc.credential.service.url={i['credential_service_url']}",
            "edc.iam.did.web.use.https=true",
        ]
    ) + "\n"
