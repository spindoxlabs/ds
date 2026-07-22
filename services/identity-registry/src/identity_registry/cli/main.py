from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from ..config import get_settings
from ..db.engine import get_engine, get_session_factory, init_db
from ..db.models import Credential, Did, Key, KeycloakMapping, OrganizationMembership, Owner, Participant, StatusList
from ..services.crypto import (
    decrypt_private_jwk,
    encrypt_private_jwk,
    generate_credential_id,
    generate_key_pair,
    hash_sts_secret,
)
from ..services.status_list import create_bitstring, next_available_index, set_bit
from ..services.vc import build_membership_credential, sign_credential

app = typer.Typer(name="ir-cli", help="Identity Registry CLI")
participant_app = typer.Typer(help="Participant management")
credential_app = typer.Typer(help="Credential management")
key_app = typer.Typer(help="Key management")
status_app = typer.Typer(help="Status list management")
keycloak_app = typer.Typer(help="Keycloak mapping management")
owner_app = typer.Typer(help="Owner registry management")
membership_app = typer.Typer(help="Organization membership management")

app.add_typer(participant_app, name="participant")
app.add_typer(credential_app, name="credential")
app.add_typer(key_app, name="key")
app.add_typer(status_app, name="status")
app.add_typer(keycloak_app, name="keycloak")
app.add_typer(owner_app, name="owner")
app.add_typer(membership_app, name="membership")


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

            kp = generate_key_pair(trust_did)
            key = Key(
                owner_did=trust_did,
                kid=kp.kid,
                private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
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
            await session.commit()

            typer.echo(f"Trust anchor bootstrapped: {trust_did}")
            typer.echo(f"  Key ID: {kp.kid}")

    _run(_bootstrap())


@participant_app.command("add")
def participant_add(
    did: str = typer.Option(..., help="Participant DID"),
    roles: str = typer.Option("consumer", help="Comma-separated roles: provider,consumer"),
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

            did_result = await session.execute(
                select(Did).where(Did.did == did)
            )
            did_record = did_result.scalar_one_or_none()

            if not did_record:
                kp = generate_key_pair(did)
                key = Key(
                    owner_did=did,
                    kid=kp.kid,
                    private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
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

            roles_list = [r.strip() for r in roles.split(",")]
            participant = Participant(
                did=did,
                dsp_address=dsp_address,
                roles=roles_list,
                allowed_scopes=list(scope),
                sts_client_secret=hash_sts_secret(sts_secret),
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

                status_list_url = (
                    f"https://{settings.trust_anchor_domain}/status/1"
                )
                ta_raw_jwk = decrypt_private_jwk(ta_key.private_jwk, settings.encryption_key)

                for r in roles_list:
                    sl_index = next_available_index(sl.bitstring)
                    cred_id = generate_credential_id()

                    vc = build_membership_credential(
                        issuer_did=trust_anchor_did,
                        subject_did=did,
                        role=r,
                        allowed_scopes=list(scope),
                        credentials_context_url=settings.credentials_context_url,
                        dataspace_uri=settings.dataspace_uri,
                        status_list_credential_url=status_list_url,
                        status_list_index=sl_index,
                        credential_id=cred_id,
                    )
                    signed_vc = sign_credential(vc, ta_raw_jwk, ta_key.kid)

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
                    sl.bitstring = set_bit(sl.bitstring, sl_index)
                    typer.echo(f"  Issued MembershipCredential ({r.capitalize()}): {cred_id}")

            await session.commit()
            typer.echo(f"Participant registered: {did} (roles={roles_list})")

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
                    f"  {p.did}  roles={p.roles}  scopes={p.allowed_scopes}  "
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

            participant.active = False
            participant.deactivated_at = datetime.now(UTC)
            await session.commit()

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
            ta_raw_jwk = decrypt_private_jwk(ta_key.private_jwk, settings.encryption_key)
            signed_vc = sign_credential(vc, ta_raw_jwk, ta_key.kid)

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
            await session.commit()

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
            existing_cred = await session.execute(
                select(Credential).where(
                    Credential.subject_did == subject_did,
                    Credential.credential_type == "DataSubjectCredential",
                    Credential.status == "active",
                )
            )
            if existing_cred.scalar_one_or_none():
                typer.echo(f"Active DataSubjectCredential already exists for {subject_did}")
                return

            ta_key_result = await session.execute(
                select(Key).where(Key.owner_did == ta_did, Key.active.is_(True))
            )
            ta_key = ta_key_result.scalar_one_or_none()
            if not ta_key:
                typer.echo("Trust anchor not bootstrapped.", err=True)
                raise typer.Exit(1)

            did_result = await session.execute(
                select(Did).where(Did.did == subject_did)
            )
            if not did_result.scalar_one_or_none():
                kp = generate_key_pair(subject_did)
                key = Key(
                    owner_did=subject_did, kid=kp.kid,
                    private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
                    public_jwk=kp.public_jwk,
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
            ta_raw_jwk = decrypt_private_jwk(ta_key.private_jwk, settings.encryption_key)
            signed_vc = sign_credential(vc, ta_raw_jwk, ta_key.kid)

            cred = Credential(
                id=cred_id, credential_type="DataSubjectCredential",
                issuer_did=ta_did, subject_did=subject_did,
                credential_json=signed_vc, status_list_index=sl_index,
                expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
            )
            session.add(cred)
            await session.commit()

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
            await session.commit()

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

            old_key.active = False
            old_key.rotated_at = datetime.now(UTC)

            kp = generate_key_pair(did, key_index=new_index)
            new_key = Key(
                owner_did=did, kid=kp.kid,
                private_jwk=encrypt_private_jwk(kp.private_jwk, settings.encryption_key),
                public_jwk=kp.public_jwk,
            )
            session.add(new_key)
            await session.flush()

            did_record.key_id = new_key.id
            await session.commit()

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


@keycloak_app.command("org-sync")
def keycloak_org_sync(
    config: Path = typer.Option(..., help="Path to organizations.yaml"),
    keycloak_url: str = typer.Option("http://172.17.0.1:9080", help="Keycloak base URL"),
    realm: str = typer.Option(None, help="Keycloak realm (default: realm from config)"),
    admin_user: str = typer.Option("admin", help="KC master-realm admin user"),
    admin_password: str = typer.Option("admin", help="KC master-realm admin password"),
    strict: bool = typer.Option(
        False, help="Exit non-zero if any configured member is missing from Keycloak"
    ),
):
    """Provision Keycloak native organizations from organizations.yaml (idempotent)."""
    from ..services.keycloak_admin import (
        KeycloakAdminClient,
        load_organizations_config,
        sync_organizations,
    )

    if not config.exists():
        typer.echo(f"Config file not found: {config}", err=True)
        raise typer.Exit(1)

    org_config = load_organizations_config(config)
    target_realm = realm or org_config.realm
    if not target_realm:
        typer.echo("No realm given — pass --realm or set 'realm' in the config", err=True)
        raise typer.Exit(1)

    async def _sync():
        kc = await KeycloakAdminClient.authenticate(
            keycloak_url,
            target_realm,
            admin_user=admin_user,
            admin_password=admin_password,
        )
        try:
            return await sync_organizations(org_config, kc)
        finally:
            await kc.aclose()

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    report = _run(_sync())

    typer.echo(
        f"Organization sync complete: "
        f"{len(report.organizations_created)} created, "
        f"{len(report.organizations_existing)} existing, "
        f"{len(report.members_added)} members added, "
        f"{len(report.groups_assigned)} group assignments"
    )
    for email in report.missing_users:
        typer.echo(f"WARNING: user not found in Keycloak: {email}", err=True)
    if strict and report.has_warnings:
        raise typer.Exit(1)


@keycloak_app.command("sync")
def keycloak_sync(
    did: str = typer.Option(..., help="User DID to map"),
    realm: str = typer.Option("dataspaces", help="Keycloak realm name"),
    user_id: str = typer.Option(..., help="Keycloak user UUID"),
    email: str = typer.Option(None, help="User email address"),
):
    """Create or update a Keycloak-to-DID mapping (idempotent)."""

    async def _sync():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            did_result = await session.execute(
                select(Did).where(Did.did == did)
            )
            if not did_result.scalar_one_or_none():
                typer.echo(f"DID not found: {did}", err=True)
                typer.echo("Issue a credential first to create the DID.", err=True)
                raise typer.Exit(1)

            result = await session.execute(
                select(KeycloakMapping).where(KeycloakMapping.did == did)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.keycloak_realm = realm
                existing.keycloak_user_id = user_id
                if email is not None:
                    existing.email = email
                existing.subject_id = did
                existing.synced_at = datetime.now(UTC)
                typer.echo(f"Updated Keycloak mapping for {did}")
            else:
                mapping = KeycloakMapping(
                    did=did,
                    keycloak_realm=realm,
                    keycloak_user_id=user_id,
                    email=email,
                    subject_id=did,
                    synced_at=datetime.now(UTC),
                )
                session.add(mapping)
                typer.echo(f"Created Keycloak mapping for {did}")

            await session.commit()

    _run(_sync())


@owner_app.command("add")
def owner_add(
    id: str = typer.Option(..., help="Owner ID (kebab-case)"),
    type: str = typer.Option("schema:Organization", help="Schema.org type CURIE"),
    name: str = typer.Option(..., help="Human-readable display name"),
    did: str = typer.Option(None, help="did:web: URI"),
    url: str = typer.Option(None, help="Canonical homepage URI"),
    alias: list[str] = typer.Option([], help="Alternative lookup keys (repeatable)"),
):
    """Register an owner (idempotent)."""

    async def _add():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(select(Owner).where(Owner.id == id))
            if result.scalar_one_or_none():
                typer.echo(f"Owner already exists: {id}")
                return

            owner = Owner(
                id=id,
                type=type,
                name=name,
                did=did,
                url=url,
                aliases=list(alias),
            )
            session.add(owner)
            await session.commit()
            typer.echo(f"Owner registered: {id} ({name})")

    _run(_add())


@owner_app.command("list")
def owner_list():
    """List all owners."""

    async def _list():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(select(Owner))
            owners = result.scalars().all()

            if not owners:
                typer.echo("No owners registered.")
                return

            for o in owners:
                uri = o.did or o.url or "-"
                typer.echo(
                    f"  {o.id}  name={o.name}  type={o.type}  "
                    f"uri={uri}  aliases={o.aliases}"
                )

    _run(_list())


@owner_app.command("remove")
def owner_remove(
    id: str = typer.Option(..., help="Owner ID to remove"),
):
    """Remove an owner."""

    async def _remove():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(select(Owner).where(Owner.id == id))
            owner = result.scalar_one_or_none()
            if not owner:
                typer.echo(f"Owner not found: {id}", err=True)
                raise typer.Exit(1)

            await session.delete(owner)
            await session.commit()
            typer.echo(f"Owner removed: {id}")

    _run(_remove())


@owner_app.command("import")
def owner_import(
    file: list[Path] = typer.Option(..., help="YAML seed file(s); later files shadow earlier"),
):
    """Bulk upsert owners from YAML seed file(s)."""

    async def _import():
        import yaml

        factory = await _ensure_db()
        from sqlalchemy import select

        entries: dict[str, dict] = {}
        for f in file:
            if not f.exists():
                typer.echo(f"File not found: {f}", err=True)
                raise typer.Exit(1)
            with f.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            for entry in data.get("owners", []):
                entries[entry["id"]] = entry

        async with factory() as session:
            count = 0
            for oid, entry in entries.items():
                result = await session.execute(
                    select(Owner).where(Owner.id == oid)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    existing.type = entry.get("type", existing.type)
                    existing.name = entry.get("name", existing.name)
                    existing.did = entry.get("did", existing.did)
                    existing.url = entry.get("url", existing.url)
                    existing.aliases = entry.get("aliases", existing.aliases)
                    org = entry.get("organization")
                    if org is not None:
                        existing.organization_config = org
                    existing.updated_at = datetime.now(UTC)
                else:
                    owner = Owner(
                        id=oid,
                        type=entry.get("type", "schema:Organization"),
                        name=entry.get("name", oid),
                        did=entry.get("did"),
                        url=entry.get("url"),
                        aliases=entry.get("aliases", []),
                        organization_config=entry.get("organization"),
                    )
                    session.add(owner)
                count += 1

            await session.commit()
            typer.echo(f"Imported {count} owner(s)")

    _run(_import())


@membership_app.command("add")
def membership_add(
    user_did: str = typer.Option(..., help="Member's DID"),
    organization: str = typer.Option(..., help="Owner alias"),
    role: str = typer.Option(None, help="Role within the org"),
):
    """Register a user as member of an organization (idempotent)."""

    async def _add():
        factory = await _ensure_db()
        from sqlalchemy import and_, select

        async with factory() as session:
            result = await session.execute(
                select(OrganizationMembership).where(
                    and_(
                        OrganizationMembership.user_did == user_did,
                        OrganizationMembership.organization_alias == organization,
                    )
                )
            )
            if result.scalar_one_or_none():
                typer.echo(f"Membership already exists: {user_did} → {organization}")
                return

            membership = OrganizationMembership(
                user_did=user_did,
                organization_alias=organization,
                role=role,
            )
            session.add(membership)
            await session.commit()
            typer.echo(f"Membership registered: {user_did} → {organization}")

    _run(_add())


@membership_app.command("list")
def membership_list(
    organization: str = typer.Option(..., help="Owner alias"),
):
    """List members of an organization."""

    async def _list():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_alias == organization
                )
            )
            memberships = result.scalars().all()
            if not memberships:
                typer.echo(f"No members in {organization}.")
                return
            for m in memberships:
                typer.echo(
                    f"  {m.user_did}  role={m.role or '-'}  status={m.status}"
                )

    _run(_list())


@membership_app.command("remove")
def membership_remove(
    user_did: str = typer.Option(..., help="Member's DID"),
    organization: str = typer.Option(..., help="Owner alias"),
):
    """Remove a membership."""

    async def _remove():
        factory = await _ensure_db()
        from sqlalchemy import and_, select

        async with factory() as session:
            result = await session.execute(
                select(OrganizationMembership).where(
                    and_(
                        OrganizationMembership.user_did == user_did,
                        OrganizationMembership.organization_alias == organization,
                    )
                )
            )
            membership = result.scalar_one_or_none()
            if not membership:
                typer.echo(f"Membership not found", err=True)
                raise typer.Exit(1)

            await session.delete(membership)
            await session.commit()
            typer.echo(f"Membership removed: {user_did} → {organization}")

    _run(_remove())


@membership_app.command("import")
def membership_import(
    community_registry: Path = typer.Option(..., help="Community registry YAML path"),
    organization: str = typer.Option(..., help="Owner alias"),
    did_prefix: str = typer.Option(None, help="DID prefix for user_id → DID mapping"),
):
    """Import memberships from a community registry YAML file."""

    async def _import():
        import yaml

        factory = await _ensure_db()
        from sqlalchemy import and_, select

        if not community_registry.exists():
            typer.echo(f"File not found: {community_registry}", err=True)
            raise typer.Exit(1)

        with community_registry.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        members = data.get("members", {})
        if not isinstance(members, dict):
            typer.echo("No 'members' dict found in file", err=True)
            raise typer.Exit(1)

        count = 0
        async with factory() as session:
            for member_id, entry in members.items():
                if not isinstance(entry, dict):
                    continue
                user_id = entry.get("user_id", member_id)
                role = entry.get("role")
                status = entry.get("status", "active")

                if did_prefix:
                    user_did_val = f"did:web:{did_prefix}:{user_id}"
                else:
                    kc_result = await session.execute(
                        select(KeycloakMapping).where(
                            KeycloakMapping.subject_id.contains(user_id)
                        )
                    )
                    kc = kc_result.scalar_one_or_none()
                    if kc:
                        user_did_val = kc.did
                    else:
                        typer.echo(f"  Skipping {user_id}: no DID mapping found")
                        continue

                existing = await session.execute(
                    select(OrganizationMembership).where(
                        and_(
                            OrganizationMembership.user_did == user_did_val,
                            OrganizationMembership.organization_alias == organization,
                        )
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                membership = OrganizationMembership(
                    user_did=user_did_val,
                    organization_alias=organization,
                    role=role,
                    status=status,
                )
                session.add(membership)
                count += 1

            await session.commit()
        typer.echo(f"Imported {count} membership(s) for {organization}")

    _run(_import())


def run():
    app()
