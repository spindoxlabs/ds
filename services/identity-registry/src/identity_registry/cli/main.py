from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from ..config import get_settings
from ..db.engine import get_engine, get_session_factory, init_db
from ..db.models import Credential, Did, Key, Participant, StatusList
from ..services.crypto import generate_credential_id, generate_key_pair
from ..services.status_list import create_bitstring, next_available_index
from ..services.vc import build_membership_credential, sign_credential

app = typer.Typer(name="ir-cli", help="Identity Registry CLI")
participant_app = typer.Typer(help="Participant management")
credential_app = typer.Typer(help="Credential management")
key_app = typer.Typer(help="Key management")
status_app = typer.Typer(help="Status list management")

app.add_typer(participant_app, name="participant")
app.add_typer(credential_app, name="credential")
app.add_typer(key_app, name="key")
app.add_typer(status_app, name="status")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _ensure_db():
    await init_db()
    return get_session_factory()


@app.command()
def bootstrap(
    did: str = typer.Option(
        None,
        help="Trust anchor DID (default: did:web:{trust_anchor_domain})",
    ),
):
    """Create trust-anchor key + DID (first-time setup, idempotent)."""

    async def _bootstrap():
        settings = get_settings()
        factory = await _ensure_db()
        trust_did = did or f"did:web:{settings.trust_anchor_domain}"

        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(
                select(Did).where(Did.did == trust_did)
            )
            if result.scalar_one_or_none():
                typer.echo(f"Trust anchor already exists: {trust_did}")
                return

            async with session.begin():
                kp = generate_key_pair(trust_did)
                key = Key(
                    owner_did=trust_did,
                    kid=kp.kid,
                    private_jwk=kp.private_jwk,
                    public_jwk=kp.public_jwk,
                )
                session.add(key)
                await session.flush()

                did_record = Did(
                    did=trust_did,
                    did_type="participant",
                    display_name="Trust Anchor",
                    key_id=key.id,
                )
                session.add(did_record)

            typer.echo(f"Trust anchor bootstrapped: {trust_did}")
            typer.echo(f"  Key ID: {kp.kid}")

    _run(_bootstrap())


@participant_app.command("add")
def participant_add(
    did: str = typer.Option(..., help="Participant DID"),
    role: str = typer.Option("consumer", help="Role: provider or consumer"),
    dsp_address: str = typer.Option(None, help="DSP protocol endpoint URL"),
    scope: list[str] = typer.Option(
        [], help="Allowed scopes (repeatable)"
    ),
    sts_secret: str = typer.Option(
        "insecure-dev-secret", help="STS client secret for this participant"
    ),
    credential_service_url: str = typer.Option(
        None, help="CredentialService endpoint URL for DID document"
    ),
):
    """Register a participant (idempotent)."""

    async def _add():
        settings = get_settings()
        factory = await _ensure_db()

        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(
                select(Participant).where(Participant.did == did)
            )
            if result.scalar_one_or_none():
                typer.echo(f"Participant already exists: {did}")
                return

            async with session.begin():
                did_result = await session.execute(
                    select(Did).where(Did.did == did)
                )
                did_record = did_result.scalar_one_or_none()

                if not did_record:
                    kp = generate_key_pair(did)
                    key = Key(
                        owner_did=did,
                        kid=kp.kid,
                        private_jwk=kp.private_jwk,
                        public_jwk=kp.public_jwk,
                    )
                    session.add(key)
                    await session.flush()

                    service_endpoints = []
                    if dsp_address:
                        service_endpoints.append(
                            {"type": "DSPEndpoint", "serviceEndpoint": dsp_address}
                        )
                    if credential_service_url:
                        service_endpoints.append(
                            {
                                "type": "CredentialService",
                                "serviceEndpoint": credential_service_url,
                            }
                        )

                    did_record = Did(
                        did=did,
                        did_type="participant",
                        key_id=key.id,
                        service_endpoints=service_endpoints or None,
                    )
                    session.add(did_record)
                    await session.flush()

                    typer.echo(f"  Created DID: {did}")
                    typer.echo(f"  Key ID: {kp.kid}")

                participant = Participant(
                    did=did,
                    dsp_address=dsp_address,
                    role=role,
                    allowed_scopes=list(scope),
                    sts_client_secret=sts_secret,
                )
                session.add(participant)

                trust_anchor_did = f"did:web:{settings.trust_anchor_domain}"
                ta_key_result = await session.execute(
                    select(Key).where(
                        Key.owner_did == trust_anchor_did,
                        Key.active.is_(True),
                    )
                )
                ta_key = ta_key_result.scalar_one_or_none()

                if ta_key:
                    sl_result = await session.execute(
                        select(StatusList).where(StatusList.id == "1")
                    )
                    sl = sl_result.scalar_one_or_none()
                    if not sl:
                        sl = StatusList(
                            id="1",
                            purpose="revocation",
                            bitstring=create_bitstring(),
                        )
                        session.add(sl)
                        await session.flush()

                    sl_index = next_available_index(sl.bitstring)
                    cred_id = generate_credential_id()
                    status_list_url = (
                        f"https://{settings.trust_anchor_domain}/status/1"
                    )

                    vc = build_membership_credential(
                        issuer_did=trust_anchor_did,
                        subject_did=did,
                        role=role,
                        allowed_scopes=list(scope),
                        credentials_context_url=settings.credentials_context_url,
                        dataspace_uri=settings.dataspace_uri,
                        status_list_credential_url=status_list_url,
                        status_list_index=sl_index,
                        credential_id=cred_id,
                    )
                    signed_vc = sign_credential(vc, ta_key.private_jwk, ta_key.kid)

                    cred = Credential(
                        id=cred_id,
                        credential_type="MembershipCredential",
                        issuer_did=trust_anchor_did,
                        subject_did=did,
                        credential_json=signed_vc,
                        status_list_index=sl_index,
                        expires_at=datetime.now(UTC) + timedelta(days=365),
                    )
                    session.add(cred)
                    typer.echo(f"  Issued MembershipCredential: {cred_id}")

            typer.echo(f"Participant registered: {did} ({role})")

    _run(_add())


@participant_app.command("list")
def participant_list():
    """List all participants."""

    async def _list():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(select(Participant))
            participants = result.scalars().all()

            if not participants:
                typer.echo("No participants registered.")
                return

            for p in participants:
                status = "active" if p.active else "inactive"
                typer.echo(
                    f"  {p.did}  role={p.role}  scopes={p.allowed_scopes}  "
                    f"status={status}"
                )

    _run(_list())


@participant_app.command("remove")
def participant_remove(
    did: str = typer.Option(..., help="Participant DID to remove"),
):
    """Deactivate a participant."""

    async def _remove():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(
                select(Participant).where(Participant.did == did)
            )
            participant = result.scalar_one_or_none()
            if not participant:
                typer.echo(f"Participant not found: {did}", err=True)
                raise typer.Exit(1)

            async with session.begin():
                participant.active = False
                participant.deactivated_at = datetime.now(UTC)

            typer.echo(f"Participant deactivated: {did}")

    _run(_remove())


@credential_app.command("issue-membership")
def credential_issue_membership(
    subject_did: str = typer.Option(..., help="Subject DID"),
    role: str = typer.Option("consumer"),
    scope: list[str] = typer.Option(["dataspaces.query"]),
    ttl_days: int = typer.Option(365),
):
    """Issue a MembershipCredential."""

    async def _issue():
        settings = get_settings()
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            ta_did = f"did:web:{settings.trust_anchor_domain}"
            ta_key_result = await session.execute(
                select(Key).where(Key.owner_did == ta_did, Key.active.is_(True))
            )
            ta_key = ta_key_result.scalar_one_or_none()
            if not ta_key:
                typer.echo("Trust anchor not bootstrapped. Run: ir-cli bootstrap", err=True)
                raise typer.Exit(1)

            async with session.begin():
                sl_result = await session.execute(
                    select(StatusList).where(StatusList.id == "1")
                )
                sl = sl_result.scalar_one_or_none()
                if not sl:
                    sl = StatusList(id="1", purpose="revocation", bitstring=create_bitstring())
                    session.add(sl)
                    await session.flush()

                sl_index = next_available_index(sl.bitstring)
                cred_id = generate_credential_id()
                status_list_url = f"https://{settings.trust_anchor_domain}/status/1"

                vc = build_membership_credential(
                    issuer_did=ta_did,
                    subject_did=subject_did,
                    role=role,
                    allowed_scopes=list(scope),
                    credentials_context_url=settings.credentials_context_url,
                    dataspace_uri=settings.dataspace_uri,
                    status_list_credential_url=status_list_url,
                    status_list_index=sl_index,
                    credential_id=cred_id,
                    ttl_days=ttl_days,
                )
                signed_vc = sign_credential(vc, ta_key.private_jwk, ta_key.kid)

                cred = Credential(
                    id=cred_id,
                    credential_type="MembershipCredential",
                    issuer_did=ta_did,
                    subject_did=subject_did,
                    credential_json=signed_vc,
                    status_list_index=sl_index,
                    expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
                )
                session.add(cred)

            typer.echo(f"Issued MembershipCredential: {cred_id}")
            typer.echo(f"  Subject: {subject_did}")

    _run(_issue())


@credential_app.command("issue-data-subject")
def credential_issue_data_subject(
    subject_id: str = typer.Option(..., help="Subject identifier"),
    role: str = typer.Option(None),
    linked_participant_did: str = typer.Option(None),
    ttl_days: int = typer.Option(365),
):
    """Issue a DataSubjectCredential."""

    async def _issue():
        settings = get_settings()
        factory = await _ensure_db()
        from sqlalchemy import select

        users_domain = settings.trust_anchor_domain.replace("trust-anchor.", "users.")
        subject_did = f"did:web:{users_domain}:{subject_id}"
        ta_did = f"did:web:{settings.trust_anchor_domain}"

        async with factory() as session:
            ta_key_result = await session.execute(
                select(Key).where(Key.owner_did == ta_did, Key.active.is_(True))
            )
            ta_key = ta_key_result.scalar_one_or_none()
            if not ta_key:
                typer.echo("Trust anchor not bootstrapped.", err=True)
                raise typer.Exit(1)

            async with session.begin():
                did_result = await session.execute(
                    select(Did).where(Did.did == subject_did)
                )
                if not did_result.scalar_one_or_none():
                    kp = generate_key_pair(subject_did)
                    key = Key(
                        owner_did=subject_did, kid=kp.kid,
                        private_jwk=kp.private_jwk, public_jwk=kp.public_jwk,
                    )
                    session.add(key)
                    await session.flush()
                    did_record = Did(did=subject_did, did_type="user", key_id=key.id)
                    session.add(did_record)
                    await session.flush()

                sl_result = await session.execute(
                    select(StatusList).where(StatusList.id == "1")
                )
                sl = sl_result.scalar_one_or_none()
                if not sl:
                    sl = StatusList(id="1", purpose="revocation", bitstring=create_bitstring())
                    session.add(sl)
                    await session.flush()

                sl_index = next_available_index(sl.bitstring)
                cred_id = generate_credential_id()

                from ..services.vc import build_data_subject_credential

                vc = build_data_subject_credential(
                    issuer_did=ta_did,
                    subject_did=subject_did,
                    role=role,
                    linked_participant_did=linked_participant_did,
                    credentials_context_url=settings.credentials_context_url,
                    dataspace_uri=settings.dataspace_uri,
                    status_list_credential_url=f"https://{settings.trust_anchor_domain}/status/1",
                    status_list_index=sl_index,
                    credential_id=cred_id,
                    ttl_days=ttl_days,
                )
                signed_vc = sign_credential(vc, ta_key.private_jwk, ta_key.kid)

                cred = Credential(
                    id=cred_id, credential_type="DataSubjectCredential",
                    issuer_did=ta_did, subject_did=subject_did,
                    credential_json=signed_vc, status_list_index=sl_index,
                    expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
                )
                session.add(cred)

            typer.echo(f"Issued DataSubjectCredential: {cred_id}")
            typer.echo(f"  Subject DID: {subject_did}")

    _run(_issue())


@credential_app.command("revoke")
def credential_revoke(
    credential_id: str = typer.Option(..., help="Credential ID to revoke"),
):
    """Revoke a credential."""

    async def _revoke():
        factory = await _ensure_db()
        from sqlalchemy import select
        from ..services.status_list import set_bit

        async with factory() as session:
            result = await session.execute(
                select(Credential).where(Credential.id == credential_id)
            )
            cred = result.scalar_one_or_none()
            if not cred:
                typer.echo(f"Credential not found: {credential_id}", err=True)
                raise typer.Exit(1)

            async with session.begin():
                cred.status = "revoked"
                cred.revoked_at = datetime.now(UTC)
                if cred.status_list_index is not None:
                    sl_result = await session.execute(
                        select(StatusList).where(StatusList.id == "1")
                    )
                    sl = sl_result.scalar_one_or_none()
                    if sl:
                        sl.bitstring = set_bit(sl.bitstring, cred.status_list_index)
                        sl.updated_at = datetime.now(UTC)

            typer.echo(f"Credential revoked: {credential_id}")

    _run(_revoke())


@credential_app.command("list")
def credential_list():
    """List all credentials."""

    async def _list():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(select(Credential))
            creds = result.scalars().all()

            if not creds:
                typer.echo("No credentials issued.")
                return

            for c in creds:
                typer.echo(
                    f"  {c.id}  type={c.credential_type}  "
                    f"subject={c.subject_did}  status={c.status}  "
                    f"expires={c.expires_at}"
                )

    _run(_list())


@key_app.command("rotate")
def key_rotate(
    did: str = typer.Option(..., help="DID to rotate key for"),
):
    """Rotate the key for a DID."""

    async def _rotate():
        settings = get_settings()
        factory = await _ensure_db()
        from sqlalchemy import select
        from ..services.crypto import next_key_index

        async with factory() as session:
            did_result = await session.execute(select(Did).where(Did.did == did))
            did_record = did_result.scalar_one_or_none()
            if not did_record:
                typer.echo(f"DID not found: {did}", err=True)
                raise typer.Exit(1)

            old_key_result = await session.execute(
                select(Key).where(Key.owner_did == did, Key.active.is_(True))
            )
            old_key = old_key_result.scalar_one_or_none()
            if not old_key:
                typer.echo(f"No active key for: {did}", err=True)
                raise typer.Exit(1)

            new_index = next_key_index(old_key.kid)

            async with session.begin():
                old_key.active = False
                old_key.rotated_at = datetime.now(UTC)

                kp = generate_key_pair(did, key_index=new_index)
                new_key = Key(
                    owner_did=did, kid=kp.kid,
                    private_jwk=kp.private_jwk, public_jwk=kp.public_jwk,
                )
                session.add(new_key)
                await session.flush()

                did_record.key_id = new_key.id

            typer.echo(f"Key rotated for {did}")
            typer.echo(f"  New: {kp.kid}")
            typer.echo(f"  Old: {old_key.kid}")

    _run(_rotate())


@status_app.command("export")
def status_export():
    """Export status list as JSON."""

    async def _export():
        factory = await _ensure_db()
        from sqlalchemy import select
        from ..services.status_list import encode_bitstring

        async with factory() as session:
            result = await session.execute(select(StatusList))
            lists = result.scalars().all()

            if not lists:
                typer.echo("No status lists.")
                return

            for sl in lists:
                data = {
                    "id": sl.id,
                    "purpose": sl.purpose,
                    "encodedList": encode_bitstring(sl.bitstring),
                    "updatedAt": sl.updated_at.isoformat() if sl.updated_at else None,
                }
                typer.echo(json.dumps(data, indent=2))

    _run(_export())


def run():
    app()
