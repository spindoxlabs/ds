"""Reconcile one offer's decisions across every connector that holds it.

An offer can be bound at more than one connector: the collecting organisation's
own, and a holder of the same subjects' data that the organisation registers at
as a collector (ADR-0015). A member's withdrawal is written to each of them, one
call per connector, and a call can fail. A withdrawal that reached one connector
and not the other leaves the other still serving.

This job reads every connector's decisions on the offer
(`GET /consent/admin/decisions`, ADR-0021) as the organisation that collected
them, and compares them per subject:

- **a withdrawal newer than a grant elsewhere is propagated** to that connector
  (`POST /consent/admin/shares`, `enabled: false`), relayed as the subject's when
  the subject withdrew and as the collector's otherwise;
- **a grant is never propagated.** A grant that reached one connector only is a
  connector serving less than it may, so it is *flagged* for the onboarding
  retry, never written here;
- a subject a connector has no decision about while another grants is flagged.

Run it as the collecting organisation (`CONNECTOR_CLIENT_ID` /
`CONNECTOR_CLIENT_SECRET`), periodically::

    python -m connector.reconcile --offer example-research \\
        --connector https://connector.rec.example.org \\
        --connector https://connector.dso.example.org

It is idempotent: a second run over a reconciled state writes nothing. It logs
counts, connector addresses and consent ids, never a subject id. The exit code
is 0 when every connector agrees (or was brought to agree), 1 when something is
flagged or a write failed, 2 on a configuration error.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("connector.reconcile")

#: The cause recorded with a withdrawal this job propagates as the collector's.
#: It reaches the row's `revocation_reason` and provenance, so it names no one.
PROPAGATED_REASON = "withdrawn at another connector holding this offer"


@dataclass
class Standing:
    """One subject's decisions on the offer at one connector."""

    granted_at: datetime | None = None
    withdrawn_at: datetime | None = None
    withdrawn_by: str | None = None
    consent_ids: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    compared: int = 0
    propagated: int = 0
    flagged: int = 0
    failed: int = 0

    @property
    def clean(self) -> bool:
        return not (self.flagged or self.failed)


def _when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _host(url: str) -> str:
    return urlsplit(url).netloc or url


def _standing(decisions: list[dict]) -> Standing:
    s = Standing()
    for d in decisions:
        s.consent_ids.append(d["consent_id"])
        if d["state"] == "granted":
            at = _when(d.get("decided_at"))
            if at and (s.granted_at is None or at > s.granted_at):
                s.granted_at = at
        else:
            at = _when(d.get("revoked_at")) or _when(d.get("decided_at"))
            if at and (s.withdrawn_at is None or at > s.withdrawn_at):
                s.withdrawn_at, s.withdrawn_by = at, d.get("decided_by")
    return s


async def read_offer(
    http: httpx.AsyncClient, base_url: str, offer_id: str, token: str
) -> dict[str, Standing]:
    """Every subject's standing on *offer_id* at one connector, all pages."""
    out: dict[str, Standing] = {}
    cursor: str | None = None
    while True:
        params = {"offer_id": offer_id, "limit": "100"}
        if cursor:
            params["cursor"] = cursor
        r = await http.get(
            f"{base_url.rstrip('/')}/consent/admin/decisions",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        page = r.json()
        for subject in page["subjects"]:
            out[subject["subject_id"]] = _standing(subject["decisions"])
        cursor = page.get("next_cursor")
        if not cursor:
            return out


async def withdraw(
    http: httpx.AsyncClient,
    base_url: str,
    offer_id: str,
    subject_id: str,
    withdrawn_by: str | None,
    token: str,
) -> None:
    body: dict = {"subject_id": subject_id, "offer_id": offer_id, "enabled": False}
    if withdrawn_by == "subject":
        body["decided_by"] = "subject"
    else:
        body["decided_by"] = "collector"
        body["reason"] = PROPAGATED_REASON
    r = await http.post(
        f"{base_url.rstrip('/')}/consent/admin/shares",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()


async def reconcile_offer(
    http: httpx.AsyncClient,
    offer_id: str,
    connectors: list[str],
    token: Callable[[], Awaitable[str]],
    *,
    dry_run: bool = False,
) -> Outcome:
    outcome = Outcome()
    views = {
        url: await read_offer(http, url, offer_id, await token()) for url in connectors
    }
    subjects = sorted(set().union(*views.values()))

    for subject_id in subjects:
        outcome.compared += 1
        here = {url: views[url].get(subject_id) for url in connectors}
        withdrawals = [
            (s.withdrawn_at, s.withdrawn_by, url)
            for url, s in here.items()
            if s is not None and s.withdrawn_at is not None
        ]
        newest = max(withdrawals, key=lambda w: w[0]) if withdrawals else None

        for url, s in here.items():
            if s is None:
                if any(o is not None and o.granted_at for o in here.values()):
                    outcome.flagged += 1
                    log.warning(
                        "offer %s: a subject granted elsewhere has no decision at "
                        "%s; not written (a grant is never propagated)",
                        offer_id,
                        _host(url),
                    )
                continue
            if s.granted_at is None:
                continue
            if newest is not None and newest[0] > s.granted_at:
                if dry_run:
                    outcome.flagged += 1
                    log.warning(
                        "offer %s: would withdraw consent %s at %s (withdrawn at %s)",
                        offer_id,
                        ",".join(s.consent_ids),
                        _host(url),
                        _host(newest[2]),
                    )
                    continue
                try:
                    await withdraw(
                        http, url, offer_id, subject_id, newest[1], await token()
                    )
                except httpx.HTTPError as exc:
                    outcome.failed += 1
                    log.error(
                        "offer %s: could not withdraw consent %s at %s: %s",
                        offer_id,
                        ",".join(s.consent_ids),
                        _host(url),
                        getattr(getattr(exc, "response", None), "status_code", exc),
                    )
                    continue
                outcome.propagated += 1
                log.info(
                    "offer %s: withdrew consent %s at %s, as at %s",
                    offer_id,
                    ",".join(s.consent_ids),
                    _host(url),
                    _host(newest[2]),
                )
            elif newest is not None:
                # A grant newer than a withdrawal elsewhere: the other connector
                # serves less than it may. Fail-closed, so only reported.
                outcome.flagged += 1
                log.warning(
                    "offer %s: consent %s at %s is newer than a withdrawal at %s; "
                    "the grant did not reach %s",
                    offer_id,
                    ",".join(s.consent_ids),
                    _host(url),
                    _host(newest[2]),
                    _host(newest[2]),
                )
    return outcome


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m connector.reconcile",
        description="Propagate withdrawals between connectors holding one offer.",
    )
    p.add_argument("--offer", action="append", required=True, help="offer id")
    p.add_argument(
        "--connector",
        action="append",
        required=True,
        help="base URL of a connector holding the offer (two or more)",
    )
    p.add_argument("--dry-run", action="store_true", help="report, write nothing")
    return p


async def _run(args: argparse.Namespace) -> int:
    from ds_auth.service_token import ServiceTokenProvider

    from .config import get_settings

    settings = get_settings()
    token = ServiceTokenProvider(
        token_url=settings.keycloak_token_url,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
    )
    clean = True
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as http:
        for offer_id in args.offer:
            try:
                outcome = await reconcile_offer(
                    http, offer_id, args.connector, token, dry_run=args.dry_run
                )
            except httpx.HTTPError as exc:
                log.error("offer %s: could not read every connector: %s", offer_id, exc)
                clean = False
                continue
            log.info(
                "offer %s: %d subject(s) compared, %d withdrawal(s) propagated, "
                "%d flagged, %d failed",
                offer_id,
                outcome.compared,
                outcome.propagated,
                outcome.flagged,
                outcome.failed,
            )
            clean = clean and outcome.clean
    return 0 if clean else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if len(set(args.connector)) < 2:
        print("--connector must name at least two connectors", file=sys.stderr)
        return 2
    from ds_obs import configure_logging

    configure_logging("ds-connector-reconcile")
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
