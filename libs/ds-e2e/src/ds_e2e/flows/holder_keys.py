"""The holder reads the data keys it serves, and their history (ADR-0022).

The community (`example-org`) registers its members' decisions at the grid
operator's connector with their supply points, as `collector-holder` does. Here
the **grid operator** reads them back — with its own organisation client, the
caller a scheduled export would use, and as the deployment operator:

    register → the holder's key list (both offers) → refusals
      → a relayed withdrawal → the list narrows → the history says when

What must hold, live:

- the list is **keys only** — none of the members' DIDs is anywhere in it;
- it is the **served** set: the use offer's list leaves out the supply point
  registered without the release it requires (`EX000E00000009`), which is the
  one fixture row nobody may read;
- the community's client (a collector), the consumer organisation's client,
  a plain service token and the grid operator's participant seat are **refused**,
  each for its own reason, while `admin@` (`connector.admin`) reads the same list;
- after a member's relayed withdrawal, the list no longer carries their supply
  point, and the history records that it was added on the grant and removed on
  the withdrawal, in that order.

Re-runnable: it withdraws the community's registrations before and after.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ds_e2e.consent import legal_basis
from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

REASON = "e2e-holder-keys"
POD_MEMBER = "EX000E00000001"
POD_DUAL = "EX000E00000002"
POD_UNADMITTED = "EX000E00000009"


class HolderKeysFlow(BaseFlow):
    name = "holder-keys"
    description = (
        "The grid operator reads, from its own connector, which supply points it "
        "may release per offer and when each was authorised and withdrawn"
    )
    rules = ("D-20",)

    # ── entry ────────────────────────────────────────────────────────────────

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)
        try:
            self.http.get(f"{s.grid_operator_connector_url}/health")
        except Exception as exc:
            result.fail_step("health", f"grid operator connector unreachable: {exc}")
            return result
        result.pass_step("health", "the grid operator's connector answers")

        try:
            self.collector = self.http.bearer_headers_for(
                s.provider_org_client_id, s.provider_org_client_secret
            )
            self.holder = self.http.bearer_headers_for(
                s.grid_operator_org_client_id, s.grid_operator_org_client_secret
            )
            self.consumer = self.http.bearer_headers_for(
                s.consumer_org_client_id, s.consumer_org_client_secret
            )
        except Exception as exc:
            result.fail_step(
                "organisation tokens",
                f"an organisation client could not authenticate — run "
                f"`ir-cli keycloak org-sync`: {exc}",
            )
            return result
        result.pass_step(
            "organisation tokens",
            "the community's, the grid operator's and the consumer organisation's "
            "own clients",
            holder=s.grid_operator_org_client_id,
        )

        self.started = datetime.now(UTC) - timedelta(seconds=60)
        if not self._reset(result, "no registration of its own"):
            return result
        if not self._register(result):
            return result

        self._expect_keys(
            result,
            "the holder lists the release keys",
            s.grid_release_offer_id,
            {POD_MEMBER, POD_DUAL},
        )
        self._expect_keys(
            result,
            "the holder lists the served use keys, not the unadmitted one",
            s.grid_use_offer_id,
            {POD_MEMBER, POD_DUAL},
        )
        self._check_refusals(result)
        self._check_operator(result)

        status, body = self._share(
            s.data_subject_id, s.grid_use_offer_id, enabled=False
        )
        if status != 200:
            result.fail_step(
                "a relayed withdrawal",
                "the member's withdrawal was not recorded",
                status_code=status,
                body=body,
            )
            return result
        result.pass_step(
            "a relayed withdrawal",
            "the community relays one member's withdrawal of the use offer",
        )
        self._expect_keys(
            result,
            "the list narrows on a withdrawal",
            s.grid_use_offer_id,
            {POD_DUAL},
        )
        self._check_history(result)

        self._reset(result, "withdraw its own registrations")
        return result

    def cleanup(self) -> None:
        try:
            s = self.settings
            self.collector = self.http.bearer_headers_for(
                s.provider_org_client_id, s.provider_org_client_secret
            )
        except Exception:
            return
        self._withdraw_all()

    # ── writes ───────────────────────────────────────────────────────────────

    def _share(
        self,
        subject: str,
        offer: str,
        *,
        enabled: bool,
        decided_by: str = "subject",
        keys: list[str] | None = None,
    ) -> tuple[int, Any]:
        body: dict[str, Any] = {
            "subject_id": subject,
            "offer_id": offer,
            "enabled": enabled,
            "decided_by": decided_by,
        }
        if enabled:
            body["legal_basis"] = legal_basis(REASON, source="e2e-community-portal")
        if keys is not None:
            body["keys"] = keys
        return self.http.raw(
            "POST",
            f"{self.settings.grid_operator_connector_url}/consent/admin/shares",
            body=body,
            headers=self.collector,
        )

    def _withdraw_all(self) -> list[str]:
        s = self.settings
        problems = []
        for subject in (s.data_subject_id, s.dual_subject_id, s.consumer_subject_id):
            for offer in (s.grid_use_offer_id, s.grid_release_offer_id):
                status, body = self._share(
                    subject, offer, enabled=False, decided_by="collector"
                )
                if status != 200:
                    problems.append(f"{subject} {offer}: {status} {body}")
        return problems

    def _reset(self, result: FlowResult, step: str) -> bool:
        problems = self._withdraw_all()
        if problems:
            result.fail_step(
                step, "the flow could not clear its own state", problems=problems
            )
            return False
        result.pass_step(step, "the community's registrations here are withdrawn")
        return True

    def _register(self, result: FlowResult) -> bool:
        s = self.settings
        writes = [
            (s.data_subject_id, s.grid_release_offer_id, POD_MEMBER),
            (s.data_subject_id, s.grid_use_offer_id, POD_MEMBER),
            (s.dual_subject_id, s.grid_release_offer_id, POD_DUAL),
            (s.dual_subject_id, s.grid_use_offer_id, POD_DUAL),
            # The use offer without the release it requires: recorded, not served.
            (s.consumer_subject_id, s.grid_use_offer_id, POD_UNADMITTED),
        ]
        for subject, offer, pod in writes:
            status, body = self._share(
                subject, offer, enabled=True, keys=[f"pod:{pod}"]
            )
            if status != 200:
                result.fail_step(
                    "register",
                    f"the community could not register {offer} for {subject}",
                    status_code=status,
                    body=body,
                )
                return False
        result.pass_step(
            "register",
            "the community registered three members' decisions with their supply "
            "points, one of them without the release its use offer requires",
            registrations=len(writes),
        )
        return True

    # ── reads ────────────────────────────────────────────────────────────────

    def _keys(self, offer: str, headers: dict[str, str]) -> tuple[int, Any]:
        return self.http.raw(
            "GET",
            f"{self.settings.grid_operator_connector_url}/consent/admin/holder/keys"
            f"?offer_id={offer}",
            headers=headers,
        )

    def _expect_keys(
        self, result: FlowResult, step: str, offer: str, pods: set[str]
    ) -> None:
        s = self.settings
        status, body = self._keys(offer, self.holder)
        if status != 200 or not isinstance(body, dict):
            result.fail_step(
                step, "the holder's read failed", status_code=status, body=body
            )
            return
        listed = {
            k.get("value") for k in body.get("keys", []) if k.get("key_type") == "pod"
        }
        text = str(body)
        leaked = [
            did
            for did in (s.data_subject_id, s.dual_subject_id, s.consumer_subject_id)
            if did in text
        ]
        if listed != pods or leaked or body.get("next_cursor") is not None:
            result.fail_step(
                step,
                "the holder's list is not the served set, or names a member",
                expected=sorted(pods),
                listed=sorted(p for p in listed if p),
                leaked=leaked or None,
            )
            return
        result.pass_step(
            step,
            "exactly the supply points the data plane serves, and no member's DID",
            offer=offer,
            recipient=body.get("recipient"),
            keys=sorted(pods),
        )

    def _check_refusals(self, result: FlowResult) -> None:
        s = self.settings
        offer = s.grid_use_offer_id
        refused: dict[str, Any] = {}
        refused["the community (a collector)"] = self._keys(offer, self.collector)
        refused["the consumer organisation"] = self._keys(offer, self.consumer)
        refused["a plain service token"] = self._keys(offer, self.http.bearer_headers())
        try:
            seat = self.http.user_headers(
                s.grid_operator_email, s.grid_operator_password
            )
            refused["the grid operator's participant seat"] = self._keys(offer, seat)
        except Exception as exc:
            refused["the grid operator's participant seat"] = (0, f"no token: {exc}")

        expected = {
            "the community (a collector)": "/consent/admin/decisions",
            "the consumer organisation": "/consent/admin/decisions",
            # The onboarding client holds no holder scope: refused on the
            # permission before its class is even asked.
            "a plain service token": "connector.consent.holder.read",
            "the grid operator's participant seat": "connector.consent.holder.read",
        }
        wrong = {
            label: (refused[label][0], _detail(refused[label][1]))
            for label, fragment in expected.items()
            if refused[label][0] != 403 or fragment not in str(refused[label][1])
        }
        if wrong:
            result.fail_step(
                "refused readers",
                "a reader the holder must refuse was not refused for the right reason",
                wrong=wrong,
            )
            return
        result.pass_step(
            "refused readers",
            "403 for a collector, another organisation, a plain service token and "
            "a participant seat without the permission — each naming its cause",
            probes=len(expected),
        )

    def _check_operator(self, result: FlowResult) -> None:
        s = self.settings
        try:
            operator = self.http.user_headers(s.admin_email, s.admin_password)
        except Exception as exc:
            result.fail_step("the deployment operator reads", f"no token: {exc}")
            return
        status, body = self._keys(s.grid_use_offer_id, operator)
        listed = (
            {k.get("value") for k in body.get("keys", [])}
            if isinstance(body, dict)
            else set()
        )
        if status != 200 or listed != {POD_MEMBER, POD_DUAL}:
            result.fail_step(
                "the deployment operator reads",
                "admin@ (connector.admin) did not read the same list",
                status_code=status,
                body=body,
            )
            return
        result.pass_step(
            "the deployment operator reads",
            "admin@ reads the same list through connector.admin — the portal's caller",
        )

    def _check_history(self, result: FlowResult) -> None:
        s = self.settings
        events: list[dict] = []
        cursor = None
        while True:
            query = f"offer_id={s.grid_use_offer_id}&since={self.started.isoformat()}"
            query = query.replace("+", "%2B")
            if cursor:
                query += f"&cursor={cursor}"
            status, body = self.http.raw(
                "GET",
                f"{s.grid_operator_connector_url}/consent/admin/holder/key-events?{query}",
                headers=self.holder,
            )
            if status != 200 or not isinstance(body, dict):
                result.fail_step(
                    "the history says when",
                    "the holder's history read failed",
                    status_code=status,
                    body=body,
                )
                return
            events.extend(body.get("events", []))
            cursor = body.get("next_cursor")
            if not cursor:
                break

        member = [
            (e.get("event"), e.get("cause"))
            for e in events
            if e.get("key") == f"pod:{POD_MEMBER}"
        ]
        # The flow's own registration and withdrawal are the last two entries
        # for this key; the reset before it may have written earlier ones.
        tail = member[-2:]
        leaked = s.data_subject_id in str(events) or s.dual_subject_id in str(events)
        if tail != [("added", "grant"), ("removed", "withdrawal")] or leaked:
            result.fail_step(
                "the history says when",
                "the history does not show the grant then the withdrawal",
                member=member,
                leaked=leaked or None,
            )
            return
        result.pass_step(
            "the history says when",
            "the member's supply point was added on the grant and removed on the "
            "withdrawal, in that order, with no member named",
            entries=len(events),
        )


def _detail(body: Any) -> Any:
    if isinstance(body, dict):
        return body.get("detail", body)
    return body
