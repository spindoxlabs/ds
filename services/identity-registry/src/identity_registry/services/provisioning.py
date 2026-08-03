"""The bundle a verified organisation needs to stand up its own ds deployment.

Everything an operator would otherwise assemble by hand: who the trust anchor is,
who the counterparties are, how to reach the dataspace's realm — and the
single-use code with which the organisation **enrols its own key**.

## What this used to be, and why that was the defect

It used to hand over an *identity*: an STS client secret this registry minted, and
`sts_token_url` / `credential_service_url` pointing at **the anchor**. So the
artefact an operator sent a third party configured that third party to use
somebody else's registry as its own Secure Token Service and credential store —
the centralized model, written into the deliverable. A DSO reading its generated
`.properties` was told, in one line, that its credential service was another
organisation's host.

It also **rotated the STS secret on every call**, which was the honest reading of
"send it again" for a secret only the registry could mint. Nothing here mints one
now (`D-51`), so the rotation is gone with the thing it protected: generating a
bundle is no longer a mutation of somebody's identity, and asking for it twice no
longer kills the first copy.

## What it is now

Three things, and none of them is a credential belonging to an identity the
recipient should have generated:

- **trust material** — the anchor's DID, the trusted issuers, the revocation list.
  This is the part that was always the point;
- **an enrolment code** — single-use, expiring, and worthless without the key the
  recipient generates itself;
- **the configuration for their own instance** — role, DID, endpoints, and the
  names of the two secrets *they* must set.

The renderers live here rather than in the API so `ir-cli` and the HTTP endpoint
emit byte-identical output — two implementations of a config template is how a
support call becomes "but mine says something different".
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import Owner, Participant
from .enrolment import create_enrolment_token

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


def _host_of(did: str) -> str:
    """`did:web:rec.example.org` → `rec.example.org`.

    The recipient's own host, which is where every DCP surface of theirs lives.
    A `did:web` may carry a path (`did:web:host:a:b`); only the host part is an
    address, so the rest is dropped rather than guessed at.
    """
    rest = did.removeprefix("did:web:")
    return rest.split(":", 1)[0].replace("%3A", ":")


async def build_bundle(
    db: AsyncSession,
    settings: Settings,
    owner: Owner,
    *,
    keycloak_client_id: str | None = None,
    keycloak_client_secret: str | None = None,
    enrolment_ttl_days: int = 14,
) -> dict[str, Any]:
    """Assemble the bundle, including a fresh enrolment code.

    Requires a **verified owner with a DID**, and no longer requires a promoted
    participant: the bundle is what an organisation configures its deployment
    from *before* it can be a participant, so demanding promotion first was
    demanding the outcome as a precondition for the means. A participant that
    already exists is reported in `participant`; one that does not is simply
    absent, and the recipient becomes one by enrolling.
    """
    if not owner.did:
        raise ProvisioningError(
            f"Owner {owner.id!r} has no DID — set the DID it will publish before "
            "issuing it a bundle",
            422,
        )

    result = await db.execute(select(Participant).where(Participant.did == owner.did))
    participant = result.scalar_one_or_none()

    # Single-use, expiring, and it grants nothing on its own: redeeming it also
    # requires a signature from the key the recipient generates. That pairing is
    # why this can be sent the way a bundle is sent, where an STS secret could
    # not be.
    enrolment = await create_enrolment_token(
        db,
        owner.id,
        ttl_days=enrolment_ttl_days,
        label=f"provisioning bundle for {owner.id}",
        created_by="provisioning-bundle",
        roles=list(participant.roles) if participant else None,
        allowed_scopes=list(participant.allowed_scopes) if participant else None,
    )

    ir = settings.public_base_url
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
            "roles": participant.roles if participant else [],
            "allowed_scopes": participant.allowed_scopes if participant else [],
            "dsp_address": participant.dsp_address if participant else None,
        },
        # **What the recipient stands up**, not what we run for them. Every URL
        # here is on *their* host once deployed; the anchor appears only under
        # `trust` and `enrolment`.
        "instance": {
            "role": "participant",
            "participant_did": owner.did,
            "did_document_url": f"https://{_host_of(owner.did)}/.well-known/did.json",
            "credential_service_url": (
                f"https://{_host_of(owner.did)}/credentials/{owner.did}"
            ),
            "sts_token_url": f"https://{_host_of(owner.did)}/sts/{owner.did}/token",
            # Named, never valued. These are the recipient's to choose — the
            # trust anchor mints neither (`D-47`, `D-51`).
            "secrets_you_must_set": [
                "IDENTITY_REGISTRY_ENCRYPTION_KEY",
                "IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET",
            ],
        },
        "enrolment": {
            "issuer_url": f"{ir}/issuer/credentials",
            "issuer_metadata_url": f"{ir}/issuer/metadata",
            # Shown once — only its hash is stored. Reissue to replace it, which
            # also invalidates the old one.
            "code": enrolment.code,
            "expires_at": (
                enrolment.expires_at.isoformat() if enrolment.expires_at else None
            ),
        },
        "trust": {
            "trust_anchor_did": trust_anchor_did,
            "trusted_issuers": [trust_anchor_did],
            "credential_status_url": f"{ir}/status/1",
            "identity_registry_url": ir,
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
    """A `.env` fragment for the third party's ds deployment.

    Two halves, and the split is the whole change: what they run, and who they
    trust. Nothing here is an identity we minted for them — the two secrets they
    need are named and left empty, because they are theirs to choose.
    """
    p, inst, t, e = (
        bundle["participant"],
        bundle["instance"],
        bundle["trust"],
        bundle["enrolment"],
    )
    kc = bundle.get("keycloak") or {}
    provider = next(
        (c for c in bundle["counterparties"] if "provider" in (c.get("roles") or [])),
        None,
    )

    lines = [
        "# Generated by ir-cli / the identity registry.",
        "# Contains a single-use enrolment code — treat it as a credential until",
        "# it is redeemed. It grants nothing on its own: redeeming it also needs a",
        "# signature from the key you generate below.",
        "",
        "# ── Your own identity registry instance ─────────────────────────────",
        f"IDENTITY_REGISTRY_ROLE={inst['role']}",
        f"IDENTITY_REGISTRY_PARTICIPANT_DID={inst['participant_did']}",
        f"IDENTITY_REGISTRY_TRUST_ANCHOR_DOMAIN={_host_of(t['trust_anchor_did'])}",
        f"IDENTITY_REGISTRY_TRUST_ANCHOR_URL={t['identity_registry_url']}",
    ]
    if p.get("dsp_address"):
        lines.append(
            f"IDENTITY_REGISTRY_PARTICIPANT_DSP_ADDRESS={p['dsp_address']}"
        )
    lines += [
        "",
        "# **Yours to choose. The trust anchor mints neither.**",
        "# Losing the encryption key makes your DID private key unrecoverable.",
        "IDENTITY_REGISTRY_ENCRYPTION_KEY=",
        "IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET=",
        "",
        "# ── Your connector and EDC ──────────────────────────────────────────",
        f"CONNECTOR_PARTICIPANT_DID={p['did']}",
        f"CONNECTOR_PARTICIPANT_ID={p['alias']}",
        "# Registry questions — who is a participant, what was issued, what was",
        "# agreed — are the trust anchor's. Only the STS and the credential",
        "# service below are yours.",
        f"CONNECTOR_IDENTITY_REGISTRY_URL={t['identity_registry_url']}",
        f"EDC_IAM_STS_OAUTH_TOKEN_URL={inst['sts_token_url']}",
        f"EDC_IAM_STS_OAUTH_CLIENT_ID={p['did']}",
        "# The same value as IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET above:",
        "# your connector authenticating to your own STS.",
        "EDC_IAM_STS_OAUTH_CLIENT_SECRET=",
        "",
        "# ── Who to trust ────────────────────────────────────────────────────",
        f"IDENTITY_REGISTRY_TRUST_ANCHOR_DID={t['trust_anchor_did']}",
    ]
    if provider:
        lines += [
            "",
            "# The provider this deployment negotiates with by default.",
            f"CONSUMER_DEFAULT_ASSIGNER={provider['did']}",
            f"CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS={provider['dsp_address']}",
        ]
    lines += [
        "",
        "# ── Enrolment ───────────────────────────────────────────────────────",
        "# Once your instance is up and serving its DID document at",
        f"#   {inst['did_document_url']}",
        "# run, on that instance:",
        f"#   ir-cli participant init --code {e['code']}",
        "# It generates your key, publishes your document, and presents proof of",
        "# control to the trust anchor. The anchor records the public half only.",
        f"# Expires: {e['expires_at'] or 'never'}",
    ]
    if kc:
        lines += [
            "",
            "# Service-to-service credentials in the dataspace realm. These are",
            "# ours to issue: they are how your connector authenticates to *our*",
            "# services, which is a different question from who you are.",
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

    Every URL is now on the recipient's **own** host. It used to name the trust
    anchor's, which is what made this file the clearest statement of the
    centralized model: a generated config telling a participant that its
    credential service was another organisation's.
    """
    p, inst, t = bundle["participant"], bundle["instance"], bundle["trust"]
    return "\n".join(
        [
            "# Generated by ir-cli / the identity registry.",
            "# Secrets are supplied as environment variables — see the .env fragment.",
            "",
            f"edc.participant.id={p['did']}",
            f"edc.iam.issuer.id={p['did']}",
            "# Your own Secure Token Service and credential store.",
            f"edc.iam.sts.oauth.token.url={inst['sts_token_url']}",
            "edc.iam.sts.oauth.client.secret.alias=sts-client-secret",
            f"edc.credential.service.url={inst['credential_service_url']}",
            "# The issuer you accept credentials from.",
            f"edc.iam.trusted-issuer.0.id={t['trust_anchor_did']}",
            "edc.iam.did.web.use.https=true",
        ]
    ) + "\n"
