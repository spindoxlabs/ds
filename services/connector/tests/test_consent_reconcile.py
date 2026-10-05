"""`python -m connector.reconcile` — one offer, several connectors, one answer.

A withdrawal written to one connector and not to another leaves the other still
serving. The job propagates the newest withdrawal over any older grant, never a
grant, flags what it will not write, and logs no subject id.
"""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from connector.reconcile import PROPAGATED_REASON, main, reconcile_offer

OWN = "https://connector.rec.example.org"
HOLDER = "https://connector.dso.example.org"
OFFER = "example-research"
SUBJECT = "did:web:rec.example.org:users:ex-00001"


def _cell(state: str, at: str, decided_by: str = "subject", cid: str = "c1") -> dict:
    return {
        "dataset_id": "datasets.gold.test",
        "consent_id": cid,
        "state": state,
        "decided_by": decided_by,
        "decided_at": at,
        "revoked_at": at if state == "withdrawn" else None,
    }


def _page(*cells: dict, subject: str = SUBJECT) -> dict:
    return {
        "offer_id": OFFER,
        "datasets": ["datasets.gold.test"],
        "limit": 100,
        "subjects": [{"subject_id": subject, "decisions": list(cells)}],
        "next_cursor": None,
    }


async def _token() -> str:
    return "org-token"


class Connectors:
    """Two fake connectors whose decisions change when a withdrawal is posted."""

    def __init__(self, own: list[dict], holder: list[dict]):
        self.cells = {OWN: own, HOLDER: holder}
        self.posts: list[tuple[str, dict]] = []

    def install(self, router: respx.Router) -> None:
        for url in (OWN, HOLDER):
            router.get(f"{url}/consent/admin/decisions").mock(
                side_effect=lambda req, url=url: httpx.Response(
                    200,
                    json=_page(*self.cells[url])
                    if self.cells[url]
                    else {**_page(), "subjects": []},
                )
            )
            router.post(f"{url}/consent/admin/shares").mock(
                side_effect=lambda req, url=url: self._withdraw(url, req)
            )

    def _withdraw(self, url: str, req: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(req.content)
        self.posts.append((url, body))
        self.cells[url] = [
            _cell("withdrawn", "2026-10-05T12:00:00+00:00", body["decided_by"])
        ]
        return httpx.Response(200, json=[])


async def _run(fake: Connectors, **kw):
    with respx.mock(assert_all_called=False) as router:
        fake.install(router)
        async with httpx.AsyncClient() as http:
            return await reconcile_offer(http, OFFER, [OWN, HOLDER], _token, **kw)


async def test_a_withdrawal_that_reached_one_connector_is_propagated(caplog):
    fake = Connectors(
        own=[_cell("withdrawn", "2026-10-02T00:00:00+00:00")],
        holder=[_cell("granted", "2026-10-01T00:00:00+00:00", "collector", "h1")],
    )
    caplog.set_level(logging.INFO, logger="connector.reconcile")
    outcome = await _run(fake)

    assert outcome.propagated == 1 and outcome.clean
    url, body = fake.posts[0]
    assert url == HOLDER
    # The member withdrew, so it is relayed as the member's (`D-15c`).
    assert body == {
        "subject_id": SUBJECT,
        "offer_id": OFFER,
        "enabled": False,
        "decided_by": "subject",
    }
    assert SUBJECT not in caplog.text and "ex-00001" not in caplog.text
    assert "h1" in caplog.text


async def test_the_collector_s_own_withdrawal_is_propagated_as_the_collector_s():
    fake = Connectors(
        own=[_cell("granted", "2026-10-01T00:00:00+00:00")],
        holder=[_cell("withdrawn", "2026-10-02T00:00:00+00:00", "collector")],
    )
    outcome = await _run(fake)
    assert outcome.propagated == 1
    url, body = fake.posts[0]
    assert url == OWN
    assert body["decided_by"] == "collector" and body["reason"] == PROPAGATED_REASON


async def test_a_second_run_writes_nothing():
    fake = Connectors(
        own=[_cell("withdrawn", "2026-10-02T00:00:00+00:00")],
        holder=[_cell("granted", "2026-10-01T00:00:00+00:00")],
    )
    await _run(fake)
    again = await _run(fake)
    assert len(fake.posts) == 1
    assert again.propagated == 0 and again.clean


async def test_a_grant_is_never_propagated_only_flagged():
    fake = Connectors(
        own=[_cell("granted", "2026-10-03T00:00:00+00:00")],
        holder=[_cell("withdrawn", "2026-10-02T00:00:00+00:00")],
    )
    outcome = await _run(fake)
    assert fake.posts == []
    assert outcome.flagged == 1 and not outcome.clean


async def test_a_subject_missing_at_one_connector_is_flagged_not_written():
    fake = Connectors(own=[_cell("granted", "2026-10-01T00:00:00+00:00")], holder=[])
    outcome = await _run(fake)
    assert fake.posts == [] and outcome.flagged == 1


async def test_a_dry_run_writes_nothing_and_says_so():
    fake = Connectors(
        own=[_cell("withdrawn", "2026-10-02T00:00:00+00:00")],
        holder=[_cell("granted", "2026-10-01T00:00:00+00:00")],
    )
    outcome = await _run(fake, dry_run=True)
    assert fake.posts == [] and outcome.flagged == 1


async def test_a_refused_withdrawal_is_a_failure():
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{OWN}/consent/admin/decisions").mock(
            return_value=httpx.Response(
                200, json=_page(_cell("withdrawn", "2026-10-02T00:00:00+00:00"))
            )
        )
        router.get(f"{HOLDER}/consent/admin/decisions").mock(
            return_value=httpx.Response(
                200, json=_page(_cell("granted", "2026-10-01T00:00:00+00:00"))
            )
        )
        router.post(f"{HOLDER}/consent/admin/shares").mock(
            return_value=httpx.Response(503)
        )
        async with httpx.AsyncClient() as http:
            outcome = await reconcile_offer(http, OFFER, [OWN, HOLDER], _token)
    assert outcome.failed == 1 and not outcome.clean


def test_one_connector_is_a_configuration_error():
    assert main(["--offer", OFFER, "--connector", OWN, "--connector", OWN]) == 2


@pytest.mark.parametrize("status", [403, 503])
async def test_an_unreadable_connector_stops_the_offer(status):
    with respx.mock() as router:
        router.get(f"{OWN}/consent/admin/decisions").mock(
            return_value=httpx.Response(status)
        )
        async with httpx.AsyncClient() as http:
            with pytest.raises(httpx.HTTPStatusError):
                await reconcile_offer(http, OFFER, [OWN, HOLDER], _token)
