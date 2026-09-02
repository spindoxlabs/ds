from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from ..config import get_settings
from ..db.engine import get_session_factory, verify_schema
from ..db.models import (
    Agreement,
    AgreementAcceptance,
    Credential,
    Did,
    Key,
    KeycloakMapping,
    OrganizationApplication,
    OrganizationMembership,
    Owner,
    Participant,
    StatusList,
)
from ..services.crypto import (
    decrypt_private_jwk,
    encrypt_private_jwk,
    generate_credential_id,
    generate_key_pair,
)
from ..services.status_list import (
    SUSPENSION_LIST_ID,
    allocate_status_list_index,
    allocate_suspendable_index,
    revoke_status_list_index,
)
from ..services.vc import build_membership_credential, sign_credential

app = typer.Typer(name="ir-cli", help="Identity Registry CLI")
participant_app = typer.Typer(help="Participant management")
credential_app = typer.Typer(help="Credential management")
key_app = typer.Typer(help="Key management")
status_app = typer.Typer(help="Status list management")
keycloak_app = typer.Typer(help="Keycloak mapping management")
owner_app = typer.Typer(help="Owner registry management")
membership_app = typer.Typer(help="Organization membership management")
org_app = typer.Typer(help="Organisation onboarding (Block D)")
agreement_app = typer.Typer(help="Service-agreement management")
conformity_app = typer.Typer(help="Conformity assessment (DSSC-TRF-02…-04)")

app.add_typer(participant_app, name="participant")
app.add_typer(credential_app, name="credential")
app.add_typer(key_app, name="key")
app.add_typer(status_app, name="status")
app.add_typer(keycloak_app, name="keycloak")
app.add_typer(owner_app, name="owner")
app.add_typer(membership_app, name="membership")
app.add_typer(org_app, name="org")
app.add_typer(agreement_app, name="agreement")
app.add_typer(conformity_app, name="conformity")


def _run(coro):
    """Run one command's coroutine.

    `asyncio.get_event_loop()` is deprecated from 3.12 when no loop is running
    and is scheduled to start raising; it also returned a loop nothing ever
    closed. `asyncio.run` owns the loop for the call and tears it down, which
    is the right shape here because every `ir-cli` command is one shot.
    """
    return asyncio.run(coro)


async def _ensure_db():
    await verify_schema()
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

        from ..services import anchor_bootstrap, trust_list

        async with factory() as session:
            # The key, the published document and the trust-list entry in one
            # transaction: an anchor with a key and no accreditation publishes a
            # list saying it accredits nobody, and every credential it goes on to
            # issue reads as coming from an unlisted issuer.
            identity = await anchor_bootstrap.ensure_identity(
                session, settings, did=did
            )
            await trust_list.ensure_own_anchor(session, settings)
            await session.commit()

        verb = "bootstrapped" if identity.created else "already exists —"
        typer.echo(f"Trust anchor {verb} {identity.did}")
        typer.echo(f"  Key ID: {identity.kid}")
        for entry in identity.service_endpoints:
            typer.echo(f"  {entry['type']}: {entry['serviceEndpoint']}")
        typer.echo("  Listed in the dataspace trust list (DSSC-TRF-05)")

    _run(_bootstrap())


@participant_app.command("add")
def participant_add():
    """**Removed** (`D-51`). A participant is enrolled, not added.

    This minted a participant's DID keypair *and* its STS client secret in the
    anchor's database, so the anchor could sign as any participant and decided
    how each one authenticated to a service the anchor does not run. That is the
    whole of the `§3.1` custody deviation, and it is the last operator path that
    still did it.

    The replacement is a two-party handshake:

        # trust anchor, once the organisation is verified
        ir-cli org enrolment-token --alias <owner> --roles provider

        # the organisation's **own** instance
        ir-cli participant init --code <code>

    The command is kept as a refusal rather than deleted, because a runbook, a
    chart hook or a script that still calls it should be told what replaced it —
    a bare "no such command" would read as a broken image.
    """
    typer.echo(
        "`ir-cli participant add` is removed: the trust anchor no longer mints "
        "participant keys or STS secrets (D-51).\n"
        "\n"
        "  On the anchor:       ir-cli org enrolment-token --alias <owner> "
        "--roles provider\n"
        "  On the participant:  ir-cli participant init --code <code>\n"
        "\n"
        "The participant generates its own key, publishes its own DID document, "
        "and proves control of it. The anchor records the public half.",
        err=True,
    )
    raise typer.Exit(2)


@participant_app.command("init")
def participant_init(
    did: str = typer.Option(None, help="DID to hold (default: PARTICIPANT_DID)"),
    code: str = typer.Option(
        None,
        help="Enrolment code from the trust anchor. Omit to only generate the key.",
    ),
):
    """Generate **this instance's own** DID key, then enrol it with the anchor.

    The participant half of the handshake, and the command that makes the split
    real: the keypair is generated here, encrypted with this instance's own
    encryption key, and never leaves. The anchor is sent a *signature*, not a key.

    Idempotent. Re-running keeps the existing key — a bootstrap that rotated on
    every pod start would invalidate every credential bound to the old key,
    silently. Rotation is `ir-cli key rotate`, deliberately.

    With no ``--code`` it stops after generating the identity, which is the right
    thing on a restart: the instance is already enrolled and the code is spent.
    """
    from ..services import participant_bootstrap as boot

    async def _init():
        settings = get_settings()
        factory = await _ensure_db()
        async with factory() as session:
            try:
                identity = await boot.ensure_identity(session, settings, did=did)
                await session.commit()
            except boot.ParticipantBootstrapError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc

            typer.echo(
                f"{'Generated' if identity.created else 'Already held'}: "
                f"{identity.did} (kid={identity.kid})"
            )
            for endpoint in identity.service_endpoints:
                typer.echo(
                    f"  publishes {endpoint['type']}: {endpoint['serviceEndpoint']}"
                )

            if not code:
                typer.echo("No --code given; not enrolling.")
                return

            try:
                result = await boot.enrol(
                    session, settings, code=code, did=identity.did
                )
            except boot.ParticipantBootstrapError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            typer.echo(
                f"Enrolled with {settings.issuer_base_url}: "
                f"{result.status} (issuerPid={result.issuer_pid})"
            )

    _run(_init())


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


@agreement_app.command("accept")
def agreement_accept(
    owner: str = typer.Option(..., help="Owner id or alias"),
    agreement_id: str = typer.Option("dataspace-participation", "--id"),
    version: str = typer.Option(None, help="Default: the newest imported version"),
    locale: str = typer.Option("en"),
    accepted_by: str = typer.Option(None, help="Who accepted, for the record"),
):
    """Record an organisation's acceptance of an agreement version (idempotent).

    The API has had this since Block D (`POST /admin/owners/{alias}/agreement`);
    the CLI did not, so the one step of `P-1`'s chain that a seed cannot reach
    through `owner import` had no non-HTTP path — and **no dev participant had
    ever accepted anything**, which is what `ir-cli conformity check` reported
    the first time it ran.

    Stores the agreement's id, version, locale and text SHA-256 — never the
    prose. What was accepted has to be provable years later; the text is the
    agreement's, not this registry's, to keep.
    """
    from ..services import org_onboarding as ops

    async def _accept():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            found = await ops.resolve_owner(session, owner)
            if not found:
                typer.echo(f"Owner not found: {owner}", err=True)
                raise typer.Exit(1)

            query = select(Agreement).where(Agreement.id == agreement_id)
            if version:
                query = query.where(Agreement.version == version)
            rows = (
                (await session.execute(query.order_by(Agreement.version.desc())))
                .scalars()
                .all()
            )
            if not rows:
                typer.echo(
                    f"Agreement not found: {agreement_id}"
                    + (f"@{version}" if version else ""),
                    err=True,
                )
                raise typer.Exit(1)
            agreement = rows[0]

            try:
                acceptance = await ops.record_agreement_acceptance(
                    session, found, agreement, locale=locale, accepted_by=accepted_by
                )
            except ops.OrgOnboardingError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            await session.commit()
            typer.echo(
                f"{found.id} accepted {agreement.id}@{agreement.version} "
                f"({locale}) — {acceptance.text_sha256[:12]}…"
            )

    _run(_accept())


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
                typer.echo(
                    "Trust anchor not bootstrapped. Run: ir-cli bootstrap", err=True
                )
                raise typer.Exit(1)

            sl_index = await allocate_suspendable_index(session)
            cred_id = generate_credential_id()
            status_list_url = settings.status_list_url()

            vc = build_membership_credential(
                issuer_did=ta_did,
                subject_did=subject_did,
                role=role,
                allowed_scopes=list(scope),
                credentials_context_url=settings.credentials_context_url,
                dataspace_uri=settings.dataspace_uri,
                status_list_credential_url=status_list_url,
                suspension_list_credential_url=settings.status_list_url(
                    SUSPENSION_LIST_ID
                ),
                status_list_index=sl_index,
                credential_id=cred_id,
                ttl_days=ttl_days,
            )
            ta_raw_jwk = decrypt_private_jwk(
                ta_key.private_jwk, settings.encryption_key
            )
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


async def _deliver_member_credential(
    session, settings, *, custodian_did, signed_vc, credential_id, subject_id
) -> None:
    """Push a person's credential to the organisation that holds it, and say so.

    `DID-11` step 2. Not fatal on failure and deliberately so: a bootstrap that
    issued and could not deliver has done something worth reporting, not worth
    aborting on — the credential row is what a re-run re-delivers.
    """
    from ..services.issuance import IssuanceError, deliver_to_custodian

    try:
        endpoint = await deliver_to_custodian(
            session,
            settings,
            custodian_did=custodian_did,
            credentials=[("DataSubjectCredential", signed_vc)],
            issuer_pid=credential_id,
            holder_pid=subject_id,
        )
        await session.commit()
        typer.echo(f"  Delivered to: {endpoint}")
    except IssuanceError as exc:
        typer.echo(f"  NOT delivered: {exc.message}", err=True)


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

        # The person lives in their custodian's namespace (`D-50`), and the
        # first organisation to onboard them decides which — the same rule the
        # API applies, in the same helper, so the two cannot drift.
        from ..services.did import SubjectNamespaceError, subject_did_for, subject_id_of

        try:
            subject_did = subject_did_for(linked_participant_did, subject_id)
        except SubjectNamespaceError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2) from exc
        ta_did = f"did:web:{settings.trust_anchor_domain}"

        async with factory() as session:
            existing_did = (
                (await session.execute(select(Did.did).where(Did.did_type == "user")))
                .scalars()
                .all()
            )
            for known in existing_did:
                if subject_id_of(known) == subject_id:
                    subject_did = known
                    break

            existing_cred = await session.execute(
                select(Credential).where(
                    Credential.subject_did == subject_did,
                    Credential.credential_type == "DataSubjectCredential",
                    Credential.status == "active",
                )
            )
            # Idempotent **per role**, not per subject. One person legitimately
            # holds several — a data subject about their own consumption who is
            # also a consumer user acting for an organisation — and keying this
            # on `credential_type` alone silently skipped the second issuance,
            # making a dual-role user impossible to create. `credential_type`
            # cannot carry the role: it is also the VC `type` (services/vc.py)
            # that DCP presentation matching keys on.
            for cred in existing_cred.scalars().all():
                subject = (cred.credential_json or {}).get("credentialSubject") or {}
                if subject.get("role") == role:
                    typer.echo(
                        f"Active DataSubjectCredential with role={role or '-'} "
                        f"already exists for {subject_did}"
                    )
                    # **Re-deliver, do not re-mint.** Returning here left the one
                    # state a re-run is supposed to repair unrepairable: a
                    # credential the anchor issued and the custodian never
                    # received. Signing is local and delivery is a call to
                    # somebody else's service, so those fail independently — and
                    # the holder's Storage API is idempotent on credential id,
                    # which is what makes re-delivery free rather than a
                    # duplicate.
                    await _deliver_member_credential(
                        session,
                        settings,
                        custodian_did=linked_participant_did,
                        signed_vc=cred.credential_json,
                        credential_id=cred.id,
                        subject_id=subject_id,
                    )
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
                # No keypair (`D-49`) — see `api/v1/admin.py`. The DID row still
                # exists because the DID must resolve; its document asserts no
                # verification method.
                did_record = Did(did=subject_did, did_type="user", key_id=None)
                session.add(did_record)
                await session.flush()

            sl_index = await allocate_status_list_index(session)
            cred_id = generate_credential_id()

            from ..services.vc import build_data_subject_credential

            vc = build_data_subject_credential(
                issuer_did=ta_did,
                subject_did=subject_did,
                role=role,
                linked_participant_did=linked_participant_did,
                credentials_context_url=settings.credentials_context_url,
                dataspace_uri=settings.dataspace_uri,
                status_list_credential_url=settings.status_list_url(),
                status_list_index=sl_index,
                credential_id=cred_id,
                ttl_days=ttl_days,
            )
            ta_raw_jwk = decrypt_private_jwk(
                ta_key.private_jwk, settings.encryption_key
            )
            signed_vc = sign_credential(vc, ta_raw_jwk, ta_key.kid)

            cred = Credential(
                id=cred_id,
                credential_type="DataSubjectCredential",
                issuer_did=ta_did,
                subject_did=subject_did,
                credential_json=signed_vc,
                status_list_index=sl_index,
                expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
            )
            session.add(cred)
            await session.commit()

            typer.echo(f"Issued DataSubjectCredential: {cred_id}")
            typer.echo(f"  Subject DID: {subject_did}")

            await _deliver_member_credential(
                session,
                settings,
                custodian_did=linked_participant_did,
                signed_vc=signed_vc,
                credential_id=cred_id,
                subject_id=subject_id,
            )

    _run(_issue())


@conformity_app.command("check")
def conformity_check(
    did: str = typer.Option(None, help="Assess one participant instead of all"),
    criteria: str = typer.Option(
        None, help="Criteria file (default: IDENTITY_REGISTRY_CONFORMITY_CRITERIA_PATH)"
    ),
    json_out: bool = typer.Option(False, "--json", help="Emit the report as JSON"),
):
    """Assess every participant against the rulebook — `DSSC-TRF-02`…`-04`.

    **Exits non-zero when anybody is non-conformant**, which is what makes this
    runnable as the periodic check the blueprint asks for: a cron entry, a CI
    job, a Kubernetes CronJob. A check that always exits 0 is a check nothing
    watches.

    It changes nothing. Onboarding decides whether a party may join; this asks
    whether it still qualifies, and acting on the answer — suspension — is a
    decision somebody makes with this as the evidence.
    """

    async def _check():
        settings = get_settings()
        factory = await _ensure_db()
        from ..services import conformity as conf

        path = criteria or settings.conformity_criteria_path
        try:
            rules = conf.load_criteria(path)
        except conf.ConformityError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2) from exc

        async with factory() as session:
            if did:
                from sqlalchemy import select

                participant = (
                    await session.execute(
                        select(Participant).where(Participant.did == did)
                    )
                ).scalar_one_or_none()
                if participant is None:
                    typer.echo(f"{did} is not a participant", err=True)
                    raise typer.Exit(2)
                reports = [await conf.assess(session, settings, participant, rules)]
            else:
                reports = await conf.assess_all(session, settings, rules)

        if json_out:
            typer.echo(json.dumps(conf.render(reports, settings), indent=2))
        else:
            typer.echo(f"Conformity against {path} ({len(rules)} criteria)")
            for r in reports:
                mark = "OK  " if r.status == conf.CONFORMANT else "FAIL"
                typer.echo(f"  {mark} {r.did}  [{', '.join(r.roles) or 'no role'}]")
                for f in r.failures:
                    typer.echo(f"         {f.rule}: {f.detail}")
            bad = [r for r in reports if r.status == conf.NON_CONFORMANT]
            typer.echo(
                f"\n{len(reports) - len(bad)} conformant, {len(bad)} non-conformant"
            )

        if any(r.status == conf.NON_CONFORMANT for r in reports):
            raise typer.Exit(1)

    _run(_check())


@credential_app.command("revoke")
def credential_revoke(
    credential_id: str = typer.Option(..., help="Credential ID to revoke"),
):
    """Revoke a credential."""

    async def _revoke():
        factory = await _ensure_db()
        from sqlalchemy import select

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
                await revoke_status_list_index(session, cred.status_list_index)
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
                owner_did=did,
                kid=kp.kid,
                private_jwk=encrypt_private_jwk(
                    kp.private_jwk, settings.encryption_key
                ),
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


@key_app.command("custody-check")
def key_custody_check():
    """Report every private key this instance holds, and exit non-zero on a foreign one.

    The operator-facing half of the startup sweep, so the invariant can be
    checked without restarting a registry — and so it can gate a deployment, the
    same way `ir-cli status check-indices` does.

    A **foreign** key is a private key for a DID this instance does not publish:
    it means this instance can sign and present as that participant, which is
    the deviation `D-47` and `D-51` exist to end.
    """
    from ..services.custody import REMEDIATION, audit_custody, describe

    async def _check():
        settings = get_settings()
        factory = await _ensure_db()
        async with factory() as session:
            report = await audit_custody(session, settings)

        for key in report.own:
            typer.echo(f"own       {key.did}")
        for key in report.subjects:
            typer.echo(f"subject   {key.did}   (declared D-49 deviation)")
        for key in report.foreign:
            typer.echo(f"FOREIGN   {key.did}   ({key.did_type}, kid={key.kid})")

        if report.ok:
            typer.echo(
                f"\nOK — {report.summary()}. This instance signs only as itself."
            )
            return

        typer.echo("", err=True)
        for line in describe(report, settings):
            typer.echo(line, err=True)
        typer.echo(f"\n{REMEDIATION}", err=True)
        raise typer.Exit(1)

    _run(_check())


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


@status_app.command("check-indices")
def status_check_indices():
    """Report credentials sharing a StatusList index.

    A collision means revoking any one of the group revokes all of them. It is
    left behind by the pre-0011 allocator, which read the revocation register
    for a free slot instead of a counter.

    Cannot be repaired in place: the index is inside the signed credential, so
    correcting it invalidates the signature. Affected credentials must be
    RE-ISSUED — in dev, re-run `ir-cli bootstrap`.

    Exits non-zero when duplicates are found, so it can gate a deployment.
    """

    async def _check():
        factory = await _ensure_db()

        from ..services.status_list import find_duplicate_indices

        async with factory() as session:
            duplicates = await find_duplicate_indices(session)

        if not duplicates:
            typer.echo("No duplicate StatusList indices.")
            return

        affected = sum(len(d.credential_ids) for d in duplicates)
        noun = "index" if len(duplicates) == 1 else "indices"
        typer.echo(
            f"{affected} credentials share {len(duplicates)} StatusList {noun}.",
            err=True,
        )
        for d in duplicates:
            typer.echo(f"  {d}", err=True)
            for cred_id in d.credential_ids:
                typer.echo(f"    {cred_id}", err=True)
        typer.echo(
            "\nRevoking one of a group revokes the whole group. The index is "
            "inside the\nsigned credential and cannot be corrected in place — "
            "these must be re-issued.\nIn dev: ir-cli bootstrap",
            err=True,
        )
        raise typer.Exit(1)

    _run(_check())


@keycloak_app.command("org-sync")
def keycloak_org_sync(
    config: Path = typer.Option(..., help="Path to organizations.yaml"),
    keycloak_url: str = typer.Option(
        "http://172.17.0.1:9080", help="Keycloak base URL"
    ),
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
        typer.echo(
            "No realm given — pass --realm or set 'realm' in the config", err=True
        )
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


@keycloak_app.command("map-user")
def keycloak_map_user(
    did: str = typer.Option(..., help="User DID to map"),
    realm: str = typer.Option("dataspaces", help="Keycloak realm name"),
    user_id: str = typer.Option(..., help="Keycloak user UUID"),
    email: str = typer.Option(None, help="User email address"),
    username: str = typer.Option(
        None,
        help=(
            "Keycloak preferred_username — how systems outside the dataspace "
            "name this person (the REC registry keys members on it). Defaults "
            "to the email, which is what this realm uses."
        ),
    ),
):
    """Create or update a Keycloak-to-DID mapping (idempotent).

    Local bookkeeping only — this writes a `keycloak_mappings` row and never
    contacts Keycloak. It was called `keycloak sync`, which is the name of a
    real realm-syncing command (`celine-policies keycloak sync`) invoked a few
    lines away in the same compose bootstrap; a reader had every reason to
    believe this one applied something to a realm, and nothing here says
    otherwise. Realm writes live in `services/keycloak_admin.py`.
    """

    async def _sync():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            did_result = await session.execute(select(Did).where(Did.did == did))
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
                if username is not None:
                    existing.username = username
                existing.subject_id = did
                existing.synced_at = datetime.now(UTC)
                typer.echo(f"Updated Keycloak mapping for {did}")
            else:
                mapping = KeycloakMapping(
                    did=did,
                    keycloak_realm=realm,
                    keycloak_user_id=user_id,
                    email=email,
                    # Falls back to the email because this realm sets
                    # username = email. Recorded explicitly rather than left
                    # null so the resolution does not depend on that staying true.
                    username=username or email,
                    subject_id=did,
                    synced_at=datetime.now(UTC),
                )
                session.add(mapping)
                typer.echo(f"Created Keycloak mapping for {did}")

            await session.commit()

    _run(_sync())


def _owner_verification_fields(
    *,
    status: str | None,
    verified_by: str | None,
    verified_at: datetime | None,
    evidence_ref: str | None,
    context: str,
) -> dict:
    """Resolve and validate an owner's verification claim for a CLI/seed path.

    'verified' must carry its evidence — the same invariant the DB CHECK and the
    admin API enforce — so a seeded owner cannot read as verified for free.
    Omitting ``status`` yields 'pending'.
    """
    from ..schemas.requests import VALID_OWNER_STATUSES

    resolved = status or "pending"
    if resolved not in VALID_OWNER_STATUSES:
        typer.echo(
            f"{context}: invalid status {resolved!r}; "
            f"must be one of {sorted(VALID_OWNER_STATUSES)}",
            err=True,
        )
        raise typer.Exit(1)
    if resolved == "verified" and not verified_by:
        typer.echo(f"{context}: status 'verified' requires 'verified_by'", err=True)
        raise typer.Exit(1)
    if resolved == "verified" and verified_at is None:
        verified_at = datetime.now(UTC)
    return {
        "status": resolved,
        "verified_by": verified_by,
        "verified_at": verified_at,
        "evidence_ref": evidence_ref,
    }


@owner_app.command("add")
def owner_add(
    id: str = typer.Option(..., help="Owner ID (kebab-case)"),
    type: str = typer.Option("schema:Organization", help="Schema.org type CURIE"),
    name: str = typer.Option(..., help="Human-readable display name"),
    did: str = typer.Option(None, help="did:web: URI"),
    url: str = typer.Option(None, help="Canonical homepage URI"),
    alias: list[str] = typer.Option([], help="Alternative lookup keys (repeatable)"),
    status: str = typer.Option(None, help="Verification status (default: pending)"),
    verified_by: str = typer.Option(
        None, help="Who verified this owner (required when status=verified)"
    ),
    evidence_ref: str = typer.Option(
        None, help="Verification evidence reference (ticket/document id)"
    ),
):
    """Register an owner (idempotent)."""
    verification = _owner_verification_fields(
        status=status,
        verified_by=verified_by,
        verified_at=None,
        evidence_ref=evidence_ref,
        context=f"owner add {id}",
    )

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
                **verification,
            )
            session.add(owner)
            await session.commit()
            typer.echo(f"Owner registered: {id} ({name}) [{verification['status']}]")

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


def _refuse_dev_dids(pairs: list[tuple[str, str]]) -> None:
    """Refuse a seed carrying a machine-local DID when this is production.

    A `did:web` is a URL, so a `.localhost` DID is not merely cosmetic in
    production — it is an identity that resolves nowhere, written into owner
    rows, then into issued credentials and recorded provenance, where correcting
    it destroys the evidence it was recorded as. Nothing on the resolve/export
    path fetches it, so the mistake surfaces only at negotiation, long after
    those records are made.

    `DS_ENV` defaults to production when unset (`ds_auth.production`), so
    forgetting the variable refuses rather than permits. In dev this is silent:
    the dev DIDs *are* `.localhost`, and that is correct there.

    Every violation is reported before exiting — a fourteen-owner deployment file
    is fixed in one pass, the same shape as `ProductionGuard` and the selection
    errors beside it.
    """
    # `ds-auth` ships no `py.typed`, so mypy skips it — the same silence the
    # other `ds_auth` imports in this tree carry.
    from ds_auth.production import is_production  # type: ignore[import-untyped]

    from ..services.did import dev_only_did_reason

    if not is_production():
        return

    violations: list[tuple[str, str, str]] = []
    for alias, did in pairs:
        if not did:
            continue
        reason = dev_only_did_reason(did)
        if reason:
            violations.append((alias, did, reason))
    if not violations:
        return

    typer.echo(
        "DS_ENV=production, and this seed carries DIDs that only resolve on a "
        "developer's machine:",
        err=True,
    )
    for alias, did, reason in violations:
        typer.echo(f"  - {alias}: {did}\n    \u2192 {reason}", err=True)
    typer.echo(
        "A did:web is a URL: the host is the identity. Give each organisation "
        "the host it is actually served from, or run this with DS_ENV=dev.",
        err=True,
    )
    raise typer.Exit(1)


@owner_app.command("import")
def owner_import(
    file: list[Path] = typer.Option(
        ..., help="YAML seed file(s); later files shadow earlier"
    ),
):
    """Bulk upsert owners from YAML seed file(s)."""

    async def _import():
        import yaml
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

        # Before the database, deliberately: this reads the file the operator
        # passed, so it must answer on a machine with no registry to connect to
        # — a review, a CI check, a dry run before the stack exists.
        _refuse_dev_dids([(oid, e.get("did") or "") for oid, e in entries.items()])

        factory = await _ensure_db()
        async with factory() as session:
            count = 0
            for oid, entry in entries.items():
                result = await session.execute(select(Owner).where(Owner.id == oid))
                existing = result.scalar_one_or_none()

                raw_verified_at = entry.get("verified_at")
                if isinstance(raw_verified_at, str):
                    raw_verified_at = datetime.fromisoformat(raw_verified_at)

                if existing:
                    existing.type = entry.get("type", existing.type)
                    existing.name = entry.get("name", existing.name)
                    existing.did = entry.get("did", existing.did)
                    existing.url = entry.get("url", existing.url)
                    existing.aliases = entry.get("aliases", existing.aliases)
                    org = entry.get("organization")
                    if org is not None:
                        existing.organization_config = org
                    # Only touch the verification claim when the seed declares
                    # one — an upsert that omits `status` must not silently
                    # downgrade an already-verified owner to pending.
                    if "status" in entry:
                        existing_verification = _owner_verification_fields(
                            status=entry.get("status"),
                            verified_by=entry.get("verified_by"),
                            verified_at=raw_verified_at,
                            evidence_ref=entry.get("evidence_ref"),
                            context=f"owner import {oid}",
                        )
                        for field, value in existing_verification.items():
                            setattr(existing, field, value)
                    existing.updated_at = datetime.now(UTC)
                else:
                    verification = _owner_verification_fields(
                        status=entry.get("status"),
                        verified_by=entry.get("verified_by"),
                        verified_at=raw_verified_at,
                        evidence_ref=entry.get("evidence_ref"),
                        context=f"owner import {oid}",
                    )
                    owner = Owner(
                        id=oid,
                        type=entry.get("type", "schema:Organization"),
                        name=entry.get("name", oid),
                        did=entry.get("did"),
                        url=entry.get("url"),
                        aliases=entry.get("aliases", []),
                        organization_config=entry.get("organization"),
                        **verification,
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
                typer.echo(f"  {m.user_did}  role={m.role or '-'}  status={m.status}")

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
                typer.echo("Membership not found", err=True)
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


# ── Organisation onboarding (Block D §5.6) ────────────────────────
#
# Every command routes through services.org_onboarding, the same gated logic the
# HTTP API uses (§5.7 hard constraint: the CLI is the reference implementation).


async def _resolve_application(session, alias: str) -> OrganizationApplication | None:
    from sqlalchemy import select

    result = await session.execute(
        select(OrganizationApplication)
        .where(OrganizationApplication.alias == alias)
        .order_by(OrganizationApplication.created_at.desc())
    )
    return result.scalars().first()


@org_app.command("register")
def org_register(
    alias: str = typer.Option(..., help="Owner alias (kebab-case)"),
    name: str = typer.Option(..., help="Legal name"),
    registration_number: str = typer.Option(None, help="Registration number"),
    type: str = typer.Option(
        None, "--type", help="Registration type: local|EUID|EORI|vatID|leiCode"
    ),
    hq_country: str = typer.Option(None, help="HQ country code (ISO 3166-2)"),
    legal_country: str = typer.Option(None, help="Legal country code (ISO 3166-2)"),
    role: list[str] = typer.Option(["consumer"], help="Roles (repeatable)"),
    did: str = typer.Option(None, help="did:web: URI for the organisation"),
    dsp_address: str = typer.Option(None, help="DSP protocol endpoint URL"),
):
    """Create/update an organisation application (idempotent by alias)."""
    from ..schemas.requests import VALID_REGISTRATION_TYPES

    if type is not None and type not in VALID_REGISTRATION_TYPES:
        typer.echo(
            f"Invalid --type {type!r}. "
            f"Must be one of {sorted(VALID_REGISTRATION_TYPES)}",
            err=True,
        )
        raise typer.Exit(1)

    async def _register():
        from ..services import org_onboarding as ops

        # Only the options actually given. Like the HTTP intake, a *command*
        # patches what it names — an omitted `--did` on a re-register must not
        # wipe the one already recorded. A *file* (`org import`/`apply`) is the
        # full desired state and does pass every key.
        fields = {
            "legal_name": name,
            "registration_number": registration_number,
            "registration_type": type,
            "hq_country_code": hq_country,
            "legal_country_code": legal_country,
            "roles": list(role),
            "did": did,
            "dsp_address": dsp_address,
        }
        fields = {k: v for k, v in fields.items() if v is not None}

        factory = await _ensure_db()
        async with factory() as session:
            try:
                app_row, created = await ops.upsert_application(
                    session, alias, fields, defaults=fields
                )
            except ops.OrgOnboardingError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            await session.commit()
            verb = "registered" if created else "updated"
            typer.echo(f"Application {verb}: {alias} (status={app_row.status})")

    _run(_register())


@org_app.command("verify")
def org_verify(
    alias: str = typer.Option(..., help="Owner alias"),
    verified_by: str = typer.Option(..., help="Who verified (operator id)"),
    evidence_ref: str = typer.Option(None, help="Reference to verification evidence"),
):
    """Mark an application verified and promote it into an Owner row."""
    from ..services import org_onboarding as ops

    async def _verify():
        factory = await _ensure_db()
        async with factory() as session:
            app_row = await _resolve_application(session, alias)
            if app_row is None:
                typer.echo(f"No application for alias: {alias}", err=True)
                raise typer.Exit(1)
            app_row.status = "verified"
            app_row.verified_by = verified_by
            app_row.verified_at = datetime.now(UTC)
            if evidence_ref is not None:
                app_row.evidence_ref = evidence_ref
            owner = await ops.upsert_owner_from_application(
                session, app_row, verified_by=verified_by
            )
            await session.commit()
            typer.echo(f"Verified and promoted to Owner: {owner.id} (status=verified)")

    _run(_verify())


@org_app.command("agreement")
def org_agreement(
    alias: str = typer.Option(..., help="Owner alias"),
    agreement: str = typer.Option(..., help="Agreement id"),
    version: str = typer.Option(..., help="Agreement version"),
    locale: str = typer.Option("en", help="BCP 47 locale of the accepted text"),
    accepted_by: str = typer.Option(None, help="Who accepted (org contact id)"),
):
    """Record an organisation's acceptance of an agreement version."""
    from sqlalchemy import select

    from ..services import org_onboarding as ops

    async def _accept():
        factory = await _ensure_db()
        async with factory() as session:
            owner = await ops.resolve_owner(session, alias)
            if owner is None:
                typer.echo(f"Owner not found: {alias}", err=True)
                raise typer.Exit(1)
            ag_result = await session.execute(
                select(Agreement).where(
                    Agreement.id == agreement, Agreement.version == version
                )
            )
            ag = ag_result.scalar_one_or_none()
            if ag is None:
                typer.echo(f"Agreement not found: {agreement}@{version}", err=True)
                raise typer.Exit(1)
            try:
                await ops.record_agreement_acceptance(
                    session, owner, ag, locale=locale, accepted_by=accepted_by
                )
            except ops.OrgOnboardingError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            await session.commit()
            typer.echo(
                f"Accepted {agreement}@{version} for {alias} "
                f"(capacity={ag.capacity}, locale={locale})"
            )

    _run(_accept())


@org_app.command("issue-credential")
def org_issue_credential(
    alias: str = typer.Option(..., help="Owner alias"),
    ttl_days: int = typer.Option(365, help="Credential TTL in days"),
    scope: list[str] = typer.Option(["dataspaces.query"], help="Allowed scopes"),
):
    """Issue an OrganizationCredential (gate: verified + current agreement)."""
    from ..services import org_onboarding as ops

    async def _issue():
        settings = get_settings()
        factory = await _ensure_db()
        async with factory() as session:
            owner = await ops.resolve_owner(session, alias)
            if owner is None:
                typer.echo(f"Owner not found: {alias}", err=True)
                raise typer.Exit(1)
            app_row = await _resolve_application(session, alias)
            roles = (app_row.roles if app_row else None) or ["consumer"]
            dsp_address = app_row.dsp_address if app_row else None
            try:
                cred = await ops.issue_organization_credential(
                    session,
                    settings,
                    owner,
                    roles=roles,
                    allowed_scopes=list(scope),
                    dsp_address=dsp_address,
                    ttl_days=ttl_days,
                )
            except ops.OrgOnboardingError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            await session.commit()
            typer.echo(f"Issued OrganizationCredential: {cred.id}")
            typer.echo(f"  Subject: {owner.did}")

    _run(_issue())


@org_app.command("promote")
def org_promote(
    alias: str = typer.Option(..., help="Owner alias"),
    dsp_address: str = typer.Option(
        None, help="DSP endpoint (default: from application)"
    ),
    scope: list[str] = typer.Option(["dataspaces.query"], help="Allowed scopes"),
):
    """Register the org as a DSP participant (gate: valid OrganizationCredential)."""
    from ..services import org_onboarding as ops

    async def _promote():
        settings = get_settings()
        factory = await _ensure_db()
        async with factory() as session:
            owner = await ops.resolve_owner(session, alias)
            if owner is None:
                typer.echo(f"Owner not found: {alias}", err=True)
                raise typer.Exit(1)
            app_row = await _resolve_application(session, alias)
            dsp = dsp_address or (app_row.dsp_address if app_row else None)
            if not dsp:
                typer.echo(
                    "No --dsp-address given and none on the application", err=True
                )
                raise typer.Exit(1)
            roles = (app_row.roles if app_row else None) or ["consumer"]
            try:
                participant = await ops.promote_owner_to_participant(
                    session,
                    settings,
                    owner,
                    dsp_address=dsp,
                    roles=roles,
                    allowed_scopes=list(scope),
                )
            except ops.OrgOnboardingError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            await session.commit()
            typer.echo(f"Promoted to participant: {participant.did}")
            typer.echo(f"  DSP: {participant.dsp_address}  roles={participant.roles}")

    _run(_promote())


@org_app.command("list")
def org_list():
    """List organisation owners with their lifecycle state."""

    async def _list():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(
                select(Owner).where(Owner.registration_type.isnot(None))
            )
            owners = result.scalars().all()
            if not owners:
                typer.echo("No organisation owners.")
                return
            for o in owners:
                ag = (
                    f"{o.agreement_id}@{o.agreement_version}" if o.agreement_id else "-"
                )
                typer.echo(
                    f"  {o.id}  name={o.name}  status={o.status}  "
                    f"did={o.did or '-'}  agreement={ag}  "
                    f"capacity={o.agreement_capacity or '-'}"
                )

    _run(_list())


@org_app.command("show")
def org_show(
    alias: str = typer.Option(..., help="Owner alias"),
):
    """Show an organisation's owner row, application and agreement acceptances."""
    from ..services import org_onboarding as ops

    async def _show():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            owner = await ops.resolve_owner(session, alias)
            app_row = await _resolve_application(session, alias)
            if owner is None and app_row is None:
                typer.echo(f"Nothing found for alias: {alias}", err=True)
                raise typer.Exit(1)
            if owner:
                typer.echo(f"Owner: {owner.id}")
                typer.echo(f"  name={owner.name}  status={owner.status}")
                typer.echo(
                    f"  registration={owner.registration_number or '-'} "
                    f"({owner.registration_type or '-'})"
                )
                typer.echo(
                    f"  hq={owner.hq_country_code or '-'} "
                    f"legal={owner.legal_country_code or '-'}"
                )
                typer.echo(f"  did={owner.did or '-'}")
                typer.echo(
                    f"  agreement={owner.agreement_id or '-'}@"
                    f"{owner.agreement_version or '-'} "
                    f"capacity={owner.agreement_capacity or '-'}"
                )
            if app_row:
                typer.echo(f"Application: {app_row.id}  status={app_row.status}")
            acc_result = await session.execute(
                select(AgreementAcceptance).where(
                    AgreementAcceptance.owner_alias == alias
                )
            )
            acceptances = acc_result.scalars().all()
            if acceptances:
                typer.echo("Acceptances:")
                for a in acceptances:
                    typer.echo(
                        f"  {a.agreement_id}@{a.agreement_version}  "
                        f"locale={a.locale}  sha256={a.text_sha256[:12]}…"
                    )

    _run(_show())


@org_app.command("suspend")
def org_suspend(
    alias: str = typer.Option(..., help="Owner alias"),
):
    """Suspend an organisation — reversible, unlike `revoke`.

    Sets the suspension bit on every participant credential it holds and
    deactivates the participant. `org reinstate` undoes exactly this.
    """
    from ..services import org_onboarding as ops

    async def _suspend():
        factory = await _ensure_db()
        async with factory() as session:
            owner = await ops.resolve_owner(session, alias)
            if owner is None:
                typer.echo(f"Owner not found: {alias}", err=True)
                raise typer.Exit(1)
            try:
                await ops.suspend_owner(session, owner)
            except ops.OrgOnboardingError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            await session.commit()
            typer.echo(f"Suspended: {alias}")

    _run(_suspend())


@org_app.command("reinstate")
def org_reinstate(
    alias: str = typer.Option(..., help="Owner alias"),
):
    """Lift a suspension — the credentials the organisation already holds
    become valid again, unchanged and un-re-issued.

    Refused for a revoked organisation: revocation is terminal, and re-admitting
    one is a new verification, not a reinstatement.
    """
    from ..services import org_onboarding as ops

    async def _reinstate():
        factory = await _ensure_db()
        async with factory() as session:
            owner = await ops.resolve_owner(session, alias)
            if owner is None:
                typer.echo(f"Owner not found: {alias}", err=True)
                raise typer.Exit(1)
            try:
                await ops.reinstate_owner(session, owner)
            except ops.OrgOnboardingError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            await session.commit()
            typer.echo(f"Reinstated: {alias}")

    _run(_reinstate())


@org_app.command("revoke")
def org_revoke(
    alias: str = typer.Option(..., help="Owner alias"),
):
    """Revoke an organisation (terminal; StatusList bit + participant deactivation)."""
    from ..services import org_onboarding as ops

    async def _revoke():
        factory = await _ensure_db()
        async with factory() as session:
            owner = await ops.resolve_owner(session, alias)
            if owner is None:
                typer.echo(f"Owner not found: {alias}", err=True)
                raise typer.Exit(1)
            await ops.revoke_owner(session, owner)
            await session.commit()
            typer.echo(f"Revoked: {alias}")

    _run(_revoke())


@org_app.command("enrolment-token")
def org_enrolment_token(
    alias: str = typer.Option(..., help="Owner alias to enrol"),
    ttl_days: int = typer.Option(14, help="Lifetime in days"),
    label: str = typer.Option(None, help="Note for the operator: who this went to"),
    roles: str = typer.Option(
        "consumer", help="Roles this token admits: provider,consumer"
    ),
    scope: list[str] = typer.Option([], help="Allowed scopes (repeatable)"),
):
    """Issue the code a verified organisation enrols its own key with.

    The terminal step of the governance plane. What follows it is not something
    an operator does: the organisation generates its own keypair, publishes its
    own DID document, and presents this code inside a self-issued token proving
    control of that key (`POST /issuer/credentials`).

    **Printed once** — only the hash is stored. Reissue to replace a lost code,
    which also invalidates the old one.
    """
    from ..services import enrolment as enrol_service

    async def _issue():
        factory = await _ensure_db()
        async with factory() as session:
            try:
                issued = await enrol_service.create_enrolment_token(
                    session,
                    alias,
                    ttl_days=ttl_days,
                    label=label,
                    created_by="ir-cli",
                    roles=[r.strip() for r in roles.split(",") if r.strip()],
                    allowed_scopes=list(scope),
                )
            except enrol_service.EnrolmentError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            await session.commit()

        # The code on stdout alone, so a bootstrap script can capture it without
        # parsing prose; everything a person needs goes to stderr.
        typer.echo(issued.code)
        typer.echo(
            f"# Enrolment code for {alias} — expires "
            f"{issued.expires_at.isoformat() if issued.expires_at else 'never'}. "
            "Shown once; the registry stores only its hash.",
            err=True,
        )

    _run(_issue())


@org_app.command("apply")
def org_apply(
    file: Path = typer.Option(..., help="owners.yaml seed file"),
    governance: list[Path] = typer.Option(
        None,
        "--governance",
        help="Governance file(s) naming the owners to onboard. Repeatable. "
        "Requires --verified-by.",
    ),
    verified_by: str = typer.Option(
        None,
        "--verified-by",
        help="Verification evidence for entries carrying no dataspace: block — "
        "who verified them, once for the whole run.",
    ),
    evidence_ref: str = typer.Option(
        None,
        "--evidence-ref",
        help="What the run's verification rests on, e.g. the owners file and its "
        "revision. Requires --verified-by.",
    ),
    dry_run: bool = typer.Option(
        False, help="Report what would change; roll back instead of committing"
    ),
):
    """Seed organisations end to end from an owners.yaml (idempotent).

    Walks register → verify → agreement → issue-credential → promote for every
    entry carrying a ``dataspace:`` block, and skips the ones that do not — so
    the same file keeps serving its other consumers.

    **A deployment's owners.yaml has no such block on any entry**, and should not:
    that file is the deployment's own domain registry, and its schema forbids ds
    fields. Given ``--verified-by``, entries without a block become eligible too,
    onboarded as far as run-level evidence honestly supports — a verified owner
    holding its ``did`` and ``aliases``, which is the whole of what
    ``GET /owners/resolve`` needs. No agreement, no credential, no promotion:
    those are legal and topological facts a run flag must not assert.

    Which entries, then, is chosen by ``--governance`` where it is given — the
    owners named by an exposed dataset, so the onboarded set is derived from the
    data actually published rather than listed a second time — and by carrying a
    ``did`` where it is not.

    Every entry is attempted and **all** failures are reported together, then
    the command exits non-zero: an operator seeding ten organisations should get
    the whole list in one pass, not fix one and rediscover the next.
    """
    from ..services import org_onboarding as ops

    async def _apply():
        import yaml

        if not file.exists():
            typer.echo(f"File not found: {file}", err=True)
            raise typer.Exit(1)
        with file.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        entries = data.get("owners") or data.get("organizations") or []

        # Refused here rather than ignored: a --governance run with no evidence
        # would select the right organisations and then skip every one of them
        # for want of a `verified_by`, reporting a successful no-op.
        if (governance or evidence_ref) and not verified_by:
            flag = "--governance" if governance else "--evidence-ref"
            typer.echo(
                f"{flag} requires --verified-by: an entry with no dataspace: "
                "block cannot be verified without evidence, and would be skipped.",
                err=True,
            )
            raise typer.Exit(2)

        evidence = (
            ops.RunEvidence(verified_by=verified_by, evidence_ref=evidence_ref)
            if verified_by
            else None
        )
        selection = ops.select_entries(
            entries, governance_paths=list(governance or []) or None
        )
        for problem in selection.errors:
            typer.echo(f"ERROR  {problem}", err=True)
        if not selection.ok:
            raise typer.Exit(1)
        # Without run evidence the selection changes nothing: an entry it picks
        # that carries no `dataspace:` block is skipped exactly as before, so the
        # flagless invocation every current caller uses behaves identically.
        selected = {id(e) for e in selection.entries}
        # Only what this run would write. A dev-only DID on an entry the file
        # keeps for its other consumers is not this command's business.
        _refuse_dev_dids(
            [(e.get("id") or "?", e.get("did") or "") for e in selection.entries]
        )

        settings = get_settings()
        factory = await _ensure_db()
        outcomes: list[ops.ApplyOutcome] = []
        async with factory() as session:
            for entry in entries:
                chosen = id(entry) in selected
                outcome = await ops.apply_owner_entry(
                    session,
                    settings,
                    entry,
                    evidence if chosen else None,
                    # Only meaningful when this run had evidence to offer: without
                    # it every entry is skipped for the same, correct, reason.
                    skip_reason=(
                        None if chosen or evidence is None else selection.skipped_reason
                    ),
                )
                outcomes.append(outcome)
                if not outcome.ok:
                    # One bad entry must not roll back the entries that
                    # succeeded before it, nor abort the ones after.
                    await session.rollback()
                else:
                    await (session.rollback() if dry_run else session.commit())

        applied = [o for o in outcomes if o.applied]
        failed = [o for o in outcomes if not o.ok]
        for outcome in outcomes:
            typer.echo(f"{outcome.alias}:")
            for step in outcome.steps:
                typer.echo(f"  {step}")
            if outcome.error:
                typer.echo(f"  ERROR  {outcome.error}", err=True)

        changed = sum(1 for o in applied if o.ok and o.changed)
        typer.echo(
            f"\n{len(applied)} organisation(s) applied, {changed} changed, "
            f"{len(outcomes) - len(applied)} skipped, "
            f"{len(failed)} failed"
            + (" [dry-run: nothing committed]" if dry_run else "")
        )
        if failed:
            raise typer.Exit(1)

    _run(_apply())


@org_app.command("import")
def org_import(
    file: Path = typer.Option(..., help="organizations.yaml seed file"),
):
    """Bulk upsert organisation applications from a YAML seed (idempotent)."""

    async def _import():
        import yaml

        if not file.exists():
            typer.echo(f"File not found: {file}", err=True)
            raise typer.Exit(1)
        with file.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        from ..services import org_onboarding as ops

        factory = await _ensure_db()
        count = 0
        errors: list[str] = []
        async with factory() as session:
            for entry in data.get("organizations", []):
                alias = entry["alias"]
                try:
                    await ops.upsert_application(
                        session,
                        alias,
                        {
                            "legal_name": entry.get("legal_name", alias),
                            "registration_number": entry.get("registration_number"),
                            "registration_type": entry.get("registration_type"),
                            "hq_country_code": entry.get("hq_country_code"),
                            "legal_country_code": entry.get("legal_country_code"),
                            "parent_organizations": entry.get("parent_organizations"),
                            "sub_organizations": entry.get("sub_organizations"),
                            "roles": entry.get("roles", ["consumer"]),
                            "did": entry.get("did"),
                            "dsp_address": entry.get("dsp_address"),
                        },
                    )
                except ops.OrgOnboardingError as exc:
                    # Report the whole file's problems in one pass rather than
                    # turning one revision of the seed into five.
                    await session.rollback()
                    errors.append(f"{alias}: {exc.message}")
                    continue
                count += 1
            await session.commit()
        typer.echo(f"Imported {count} organisation application(s)")
        for err in errors:
            typer.echo(f"  ERROR  {err}", err=True)
        if errors:
            raise typer.Exit(1)

    _run(_import())


@agreement_app.command("import")
def agreement_import(
    file: Path = typer.Option(..., help="agreements.yaml seed file"),
):
    """Import service-agreement definitions from a YAML seed (idempotent)."""
    from ..services.agreements import import_agreements, load_agreements_file

    async def _import():
        if not file.exists():
            typer.echo(f"File not found: {file}", err=True)
            raise typer.Exit(1)
        try:
            entries = load_agreements_file(file)
        except (FileNotFoundError, ValueError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc

        factory = await _ensure_db()
        async with factory() as session:
            count = await import_agreements(session, entries)
            await session.commit()
        typer.echo(f"Imported {count} agreement version(s)")

    _run(_import())


@agreement_app.command("list")
def agreement_list():
    """List service-agreement definitions."""

    async def _list():
        factory = await _ensure_db()
        from sqlalchemy import select

        async with factory() as session:
            result = await session.execute(select(Agreement))
            agreements = result.scalars().all()
            if not agreements:
                typer.echo("No agreements.")
                return
            for a in agreements:
                typer.echo(
                    f"  {a.id}@{a.version}  capacity={a.capacity}  "
                    f"applies_to={a.applies_to}  "
                    f"locales={sorted((a.texts or {}).keys())}"
                )

    _run(_list())


def run():
    app()


@org_app.command("bundle")
def org_bundle(
    alias: str = typer.Option(..., help="Owner alias"),
    format: str = typer.Option("json", help="json | env | properties"),
):
    """Generate the bundle a verified organisation stands its own deployment up from.

    **It hands over no identity** (`DID-10`): trust material, the counterparties,
    and a single-use enrolment code. The recipient generates its own key and
    proves control of it; the two secrets it needs are named in the rendered
    config and left empty, because they are its to choose.

    Nothing rotates — the rotation protected an STS secret this registry minted,
    and it no longer mints one. Each call does issue a **new** enrolment code,
    and a code is single-use.

    Uses the same renderers as `POST /admin/owners/{alias}/provisioning-bundle`, so
    the CLI and the console cannot emit different config for the same organisation.

    Keycloak client credentials are **not** provisioned here: that needs the admin
    API, which the HTTP endpoint reaches. Use the console (or the endpoint) when a
    third party needs service-to-service credentials as well.
    """
    import json as _json

    from ..services import org_onboarding as ops
    from ..services import provisioning

    async def _bundle():
        settings = get_settings()
        factory = await _ensure_db()
        async with factory() as session:
            owner = await ops.resolve_owner(session, alias)
            if not owner:
                typer.echo(f"Owner not found: {alias}", err=True)
                raise typer.Exit(1)
            try:
                data = await provisioning.build_bundle(session, settings, owner)
            except provisioning.ProvisioningError as exc:
                typer.echo(exc.message, err=True)
                raise typer.Exit(1) from exc
            await session.commit()

        if format == "env":
            typer.echo(provisioning.render_env(data))
        elif format == "properties":
            typer.echo(provisioning.render_properties(data))
        else:
            typer.echo(_json.dumps(data, indent=2))
        typer.echo(
            f"\n# The enrolment code above is single-use and new. Any code from a "
            f"previous bundle for {alias} is still valid until redeemed or "
            "expired — reissue is not revocation.",
            err=True,
        )

    asyncio.run(_bundle())
