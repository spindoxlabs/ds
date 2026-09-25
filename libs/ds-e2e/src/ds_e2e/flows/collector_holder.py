"""A collector registers consent at the holder, and an organisation pulls.

Plan `a-collector-registers-consent-at-the-holder`. The community (`example-org`,
the REC) collects its members' consent; the grid operator holds their meter
readings. The community's **own client token** registers each member's decision
at the grid operator's connector, with the supply points the readings are stored
under — so the grid operator's data plane needs no call back to the community.
The consumer organisation then pulls with **its** own client token:

    relation → refusals → register (keys, prerequisite) → read back
      → catalogue → negotiate → transfer → EDR → rows (by key)
      → relayed withdrawal → rows narrowed → read back → the list read
      → provenance → D-15c

What must be refused, live:

- an organisation the registry does not list as a collector for the grid
  operator (the consumer organisation's token) — `403`;
- the community writing for a person who is **another organisation's** member
  (`partner-member`, `ds-e2e scenario apply`) — `403`, `D-21`;
- a participant operator's seat — the community's (`provider@`) and the grid
  operator's own (`gridops@`) — `403`: `connector.consent.provision` left
  `ds-participant-admin`;
- a use offer registered without the offer it requires: recorded, reported as
  `missing_prerequisites`, and **not admitted** — the supply point registered
  with it is the one fixture row nobody may read (`EX000E00000009`), so a
  prerequisite that was ignored returns it;
- after a relayed withdrawal (the member's, `decided_by="subject"`), the
  community deciding on its own (`decided_by="collector"`) may not lift it
  (`D-15c`);
- the list read (`GET /consent/admin/decisions`, ADR-0021) for an organisation
  the registry does not list — `403`, not an empty list. For the community it
  lists the withdrawn member as withdrawn, and the same row the per-subject
  read-back presents. It lists the member still sharing with their keys, and
  never another organisation's member, whether read as one page or page by page.

Data plane: the grid operator's own mock (`E2E_GRID_OPERATOR_MOCK_DATA_PLANE_URL`),
the only plane bound to the grid operator's connector and EDC; the step names it.

Re-runnable: it withdraws its own registrations and revokes the organisation's
own requests for the asset before and after.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any

from ds_e2e.consent import legal_basis
from ds_e2e.flows.base import BaseFlow
from ds_e2e.flows.organisation_token import (
    FINAL_NEGOTIATION_STATES,
    FINAL_TRANSFER_STATES,
)
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

PURPOSE = "FlexibilityResearch"
REASON = "e2e-collector-holder"
POD_MEMBER = "EX000E00000001"
POD_DUAL = "EX000E00000002"
#: The fixture row nobody consented for — given to the subject whose
#: registration lacks its prerequisite.
POD_UNADMITTED = "EX000E00000009"
PROVENANCE_WAIT_S = 15.0


class CollectorHolderFlow(BaseFlow):
    name = "collector-holder"
    description = (
        "The community registers its members' consent at the grid operator; the "
        "consumer organisation pulls exactly the registered supply points"
    )
    rules = ("D-14", "D-15c", "D-18", "D-19", "D-20", "D-21", "X-9")

    # ── entry ────────────────────────────────────────────────────────────────

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)
        if not self._check_services(result):
            return result
        try:
            self.collector = self.http.bearer_headers_for(
                s.provider_org_client_id, s.provider_org_client_secret
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
            "the community's and the consumer organisation's own clients",
            collector=s.provider_org_client_id,
            consumer=s.consumer_org_client_id,
        )

        if not self._check_relation(result):
            return result
        self._reset(result, "no registration of its own")
        self._check_refusals(result)
        if not self._register(result):
            return result
        self._check_read_back(result)

        agreement = self._negotiate(result)
        if agreement is None:
            return result
        transfer = self._transfer(result, agreement)
        if transfer is None:
            return result
        edr = self._edr(result, transfer)
        if edr is None:
            return result
        self._expect_pods(
            result,
            "rows by registered key",
            edr,
            agreement,
            transfer,
            {POD_MEMBER, POD_DUAL},
        )

        self._relayed_withdrawal(result)
        self._expect_pods(
            result,
            "a relayed withdrawal narrows the rows",
            edr,
            agreement,
            transfer,
            {POD_DUAL},
        )
        self._check_withdrawn_read_back(result)
        self._check_decisions_list(result)
        self._check_provenance(result)
        self._check_authority(result)

        self._reset(result, "withdraw its own registrations")
        return result

    def cleanup(self) -> None:
        try:
            s = self.settings
            self.collector = self.http.bearer_headers_for(
                s.provider_org_client_id, s.provider_org_client_secret
            )
            self.consumer = self.http.bearer_headers_for(
                s.consumer_org_client_id, s.consumer_org_client_secret
            )
        except Exception:
            return
        self._withdraw_all()
        self._revoke_own_requests()

    # ── preconditions ────────────────────────────────────────────────────────

    def _check_services(self, result: FlowResult) -> bool:
        s = self.settings
        for name, url in (
            ("grid operator connector", s.grid_operator_connector_url),
            ("consumer connector", s.consumer_connector_url),
            ("identity registry", s.identity_registry_url),
            ("grid operator data plane", s.grid_operator_mock_data_plane_url),
        ):
            try:
                self.http.get(f"{url}/health")
            except Exception as exc:
                result.fail_step("health", f"{name} unreachable: {exc}")
                return False
        result.pass_step("health", "the grid operator's stack answers")
        return True

    def _check_relation(self, result: FlowResult) -> bool:
        s = self.settings
        url = f"{s.identity_registry_url}/consent-collectors/check"
        answers = {}
        for label, collector in (
            ("community", s.provider_did),
            ("consumer", s.consumer_did),
        ):
            status, body = self.http.raw(
                "GET",
                f"{url}?"
                + urllib.parse.urlencode(
                    {"holder_did": s.grid_operator_did, "collector_did": collector}
                ),
                headers=self.http.bearer_headers(),
            )
            answers[label] = body.get("accepted") if isinstance(body, dict) else status
        if answers != {"community": True, "consumer": False}:
            result.fail_step(
                "the registry relation",
                "the grid operator must accept the community and nobody else — "
                "run `task e2e:scenario:apply`",
                answers=answers,
            )
            return False
        result.pass_step(
            "the registry relation",
            "the identity registry lists the community as a consent collector for "
            "the grid operator, and not the consumer organisation",
        )
        return True

    # ── writes ───────────────────────────────────────────────────────────────

    def _share(
        self,
        subject: str,
        offer: str,
        *,
        enabled: bool,
        decided_by: str = "subject",
        keys: list[str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        s = self.settings
        body: dict[str, Any] = {
            "subject_id": subject,
            "offer_id": offer,
            "enabled": enabled,
        }
        if decided_by:
            body["decided_by"] = decided_by
        if enabled:
            body["legal_basis"] = legal_basis(REASON, source="e2e-community-portal")
        if keys is not None:
            body["keys"] = keys
        return self.http.raw(
            "POST",
            f"{s.grid_operator_connector_url}/consent/admin/shares",
            body=body,
            headers=headers if headers is not None else self.collector,
        )

    def _subjects(self) -> list[str]:
        s = self.settings
        return [s.data_subject_id, s.dual_subject_id, s.consumer_subject_id]

    def _withdraw_all(self) -> list[str]:
        """The community withdraws, as itself, whatever it registered here.

        `decided_by="collector"` on purpose: a relayed withdrawal left by an
        earlier run is the member's and stays theirs (the escalation is one-way),
        and the next run's relayed grant — the member's — lifts either.
        """
        s = self.settings
        problems = []
        for subject in self._subjects():
            for offer in (s.grid_use_offer_id, s.grid_release_offer_id):
                status, body = self._share(
                    subject, offer, enabled=False, decided_by="collector"
                )
                if status != 200:
                    problems.append(f"{subject} {offer}: {status} {body}")
        return problems

    def _revoke_own_requests(self) -> str | None:
        s = self.settings
        status, requests = self.http.raw(
            "GET",
            f"{s.consumer_connector_url}/consumer/requests",
            headers=self.consumer,
        )
        if status != 200 or not isinstance(requests, list):
            return f"could not list the organisation's requests ({status})"
        for item in requests:
            if not isinstance(item, dict) or not item.get("can_revoke"):
                continue
            if item.get("asset_id") != s.grid_meter_asset_id:
                continue
            encoded = urllib.parse.quote(str(item.get("id")), safe="")
            self.http.raw(
                "POST",
                f"{s.consumer_connector_url}/consumer/requests/{encoded}/revoke",
                body={"reason": REASON},
                headers=self.consumer,
            )
        return None

    def _reset(self, result: FlowResult, step: str) -> None:
        problems = self._withdraw_all()
        error = self._revoke_own_requests()
        if problems or error:
            result.fail_step(
                step,
                "the flow could not clear its own state",
                problems=problems or None,
                error=error,
            )
            return
        result.pass_step(
            step,
            "the community's registrations are withdrawn and the organisation's "
            "requests for the asset revoked",
        )

    def _check_refusals(self, result: FlowResult) -> None:
        s = self.settings
        release = s.grid_release_offer_id
        refused: dict[str, Any] = {}

        status, body = self._share(
            s.data_subject_id, release, enabled=True, headers=self.consumer
        )
        refused["an organisation not on the list"] = (status, _detail(body))

        status, body = self._share(s.partner_member_id, release, enabled=True)
        refused["another organisation's member"] = (status, _detail(body))

        for label, email, password in (
            ("the community's operator seat", s.provider_email, s.provider_password),
            (
                "the grid operator's operator seat",
                s.grid_operator_email,
                s.grid_operator_password,
            ),
        ):
            try:
                seat = self.http.user_headers(email, password)
            except Exception as exc:
                refused[label] = (0, f"no token: {exc}")
                continue
            status, body = self._share(
                s.data_subject_id,
                release,
                enabled=True,
                decided_by="",
                headers=seat,
            )
            refused[label] = (status, _detail(body))

        expected = {
            "an organisation not on the list": "not an accepted consent collector",
            "another organisation's member": "not a member of organisation",
            "the community's operator seat": "Missing required permission",
            "the grid operator's operator seat": "Missing required permission",
        }
        wrong = {
            label: refused[label]
            for label, fragment in expected.items()
            if refused[label][0] != 403 or fragment not in str(refused[label][1])
        }
        if wrong:
            result.fail_step(
                "refused writers",
                "a writer the holder must refuse was not refused for the right reason",
                wrong=wrong,
            )
            return
        result.pass_step(
            "refused writers",
            "403 for an unlisted organisation, another organisation's member, and "
            "both participant operator seats — each naming its cause",
            probes=len(expected),
        )

    def _register(self, result: FlowResult) -> bool:
        s = self.settings
        writes = [
            (s.data_subject_id, s.grid_release_offer_id, [f"pod:{POD_MEMBER}"]),
            (s.data_subject_id, s.grid_use_offer_id, [f"pod:{POD_MEMBER}"]),
            (s.dual_subject_id, s.grid_release_offer_id, [f"pod:{POD_DUAL}"]),
            (s.dual_subject_id, s.grid_use_offer_id, [f"pod:{POD_DUAL}"]),
        ]
        for subject, offer, keys in writes:
            status, body = self._share(subject, offer, enabled=True, keys=keys)
            rows = body if isinstance(body, list) else []
            row = rows[0] if rows and isinstance(rows[0], dict) else {}
            if (
                status != 200
                or row.get("collector") != s.provider_did
                or row.get("decided_by") != "subject"
                or row.get("keys_supplied") is not True
                or row.get("missing_prerequisites") != []
            ):
                result.fail_step(
                    "register",
                    f"the community could not register {offer} for {subject}",
                    status_code=status,
                    body=body,
                )
                return False
        result.pass_step(
            "register",
            "the community registered two members' decisions on both offers, with "
            "their supply points; the holder recorded the community and the member "
            "as the decider",
            registrations=len(writes),
        )

        # The use offer without the release it requires.
        status, body = self._share(
            s.consumer_subject_id,
            s.grid_use_offer_id,
            enabled=True,
            keys=[f"pod:{POD_UNADMITTED}"],
        )
        row = body[0] if isinstance(body, list) and body else {}
        if status != 200 or row.get("missing_prerequisites") != [
            s.grid_release_offer_id
        ]:
            result.fail_step(
                "a missing prerequisite is reported",
                "a use offer registered without its release did not say so",
                status_code=status,
                body=body,
            )
            return False
        result.pass_step(
            "a missing prerequisite is reported",
            "recorded, and reported as waiting for the release offer",
            missing=row.get("missing_prerequisites"),
        )
        return True

    def _read_back(self, subject: str, headers: dict[str, str]) -> tuple[int, Any]:
        s = self.settings
        return self.http.raw(
            "GET",
            f"{s.grid_operator_connector_url}/consent/admin/subject-shares?"
            + urllib.parse.urlencode({"subject_id": subject}),
            headers=headers,
        )

    def _check_read_back(self, result: FlowResult) -> None:
        s = self.settings
        status, body = self._read_back(s.data_subject_id, self.collector)
        shares = {
            item.get("offer_id"): item
            for item in (body if isinstance(body, list) else [])
            if isinstance(item, dict)
        }
        own = status == 200 and all(
            shares.get(offer, {}).get("status") == "granted"
            and shares.get(offer, {}).get("keys") == [f"pod:{POD_MEMBER}"]
            for offer in (s.grid_release_offer_id, s.grid_use_offer_id)
        )
        other_status, _ = self._read_back(s.partner_member_id, self.collector)
        unlisted_status, _ = self._read_back(s.data_subject_id, self.consumer)
        if not own or other_status != 403 or unlisted_status != 403:
            result.fail_step(
                "read back",
                "the community must read back its own member, and nobody else's; an "
                "unlisted organisation reads nothing",
                own=status,
                shares=shares,
                other_member=other_status,
                unlisted=unlisted_status,
            )
            return
        result.pass_step(
            "read back",
            "the community reads back its member's decisions and keys at the grid "
            "operator — one subject, its own members only",
        )

    # ── the organisation's pull ──────────────────────────────────────────────

    def _negotiate(self, result: FlowResult) -> str | None:
        s = self.settings
        asset_id = s.grid_meter_asset_id
        try:
            catalog = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/catalog",
                    {
                        "counter_party_address": s.grid_operator_counter_party_address,
                        "counter_party_id": s.grid_operator_did,
                    },
                    headers=self.consumer,
                )
                or {}
            )
        except Exception as exc:
            result.fail_step("catalogue", str(exc))
            return None
        datasets = catalog.get("dataset") or catalog.get("dcat:dataset") or []
        if isinstance(datasets, dict):
            datasets = [datasets]
        dataset = next(
            (
                d
                for d in datasets
                if isinstance(d, dict)
                and str(d.get("@id") or d.get("id") or "") == asset_id
            ),
            None,
        )
        if dataset is None:
            result.fail_step(
                "catalogue",
                f"the grid operator does not offer {asset_id} — run "
                "`task e2e:sync-providers`",
            )
            return None
        policy = self._policy(dataset)
        result.pass_step("catalogue", "the grid operator offers the members' readings")

        try:
            negotiated = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/negotiate",
                    {
                        "counter_party_address": s.grid_operator_counter_party_address,
                        "offer_id": str(policy.get("@id") or f"{asset_id}#offer"),
                        "asset_id": asset_id,
                        "assigner": s.grid_operator_did,
                        "odrl_policy": policy or None,
                        "declared_purpose": [PURPOSE],
                        "justification_ref": REASON,
                    },
                    headers=self.consumer,
                )
                or {}
            )
            negotiation_id = str(negotiated["negotiation_id"])
        except Exception as exc:
            result.fail_step("negotiate", str(exc))
            return None
        encoded = urllib.parse.quote(negotiation_id, safe="")
        state = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/negotiations/{encoded}",
            lambda p: (
                p.get("state") in FINAL_NEGOTIATION_STATES
                and bool(p.get("contractAgreementId"))
            ),
            headers=self.consumer,
        )
        agreement = state.get("contractAgreementId")
        if not agreement:
            result.fail_step(
                "negotiate",
                "the consent-gated negotiation did not finalize — the holder should "
                "find the registered consent",
                negotiation_id=negotiation_id,
                state=state.get("state"),
                error=state.get("errorDetail") or state.get("detail"),
            )
            return None
        result.pass_step(
            "negotiate",
            "an agreement for the consumer organisation, admitted by the consent the "
            "community registered",
            agreement_id=agreement,
        )
        return str(agreement)

    def _transfer(self, result: FlowResult, agreement: str) -> str | None:
        s = self.settings
        try:
            started = (
                self.http.post(
                    f"{s.consumer_connector_url}/consumer/transfer",
                    {
                        "contract_agreement_id": agreement,
                        "counter_party_address": s.grid_operator_counter_party_address,
                        "asset_id": s.grid_meter_asset_id,
                        "connector_id": s.grid_operator_did,
                    },
                    headers=self.consumer,
                )
                or {}
            )
            transfer = str(started["transfer_id"])
        except Exception as exc:
            result.fail_step("transfer", str(exc))
            return None
        encoded = urllib.parse.quote(transfer, safe="")
        state = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/transfers/{encoded}",
            lambda p: p.get("state") in FINAL_TRANSFER_STATES,
            headers=self.consumer,
        )
        if state.get("state") not in FINAL_TRANSFER_STATES:
            result.fail_step(
                "transfer", "the transfer did not start", state=state.get("state")
            )
            return None
        result.pass_step("transfer", "the transfer started", transfer_id=transfer)
        return transfer

    def _edr(self, result: FlowResult, transfer: str) -> dict[str, Any] | None:
        s = self.settings
        encoded = urllib.parse.quote(transfer, safe="")
        status, edr = self.http.raw(
            "GET",
            f"{s.consumer_connector_url}/consumer/edr/{encoded}",
            headers=self.consumer,
        )
        if status != 200 or not isinstance(edr, dict) or not edr.get("authorization"):
            result.fail_step("EDR", "no EDR for the transfer", status_code=status)
            return None
        result.pass_step("EDR", "the EDC delivered the EDR to the consumer connector")
        return edr

    def _expect_pods(
        self,
        result: FlowResult,
        step: str,
        edr: dict[str, Any],
        agreement: str,
        transfer: str,
        expected: set[str],
    ) -> None:
        s = self.settings
        plane = s.grid_operator_mock_data_plane_url
        status, payload = self.http.post_raw(
            f"{plane}/query",
            {"sql": f"SELECT * FROM {s.grid_meter_asset_id}", "limit": 50},
            headers={
                "Authorization": str(edr["authorization"]),
                "Edc-Contract-Agreement-Id": str(edr.get("agreement_id") or agreement),
                "Edc-Transfer-Process-Id": transfer,
                "Edc-Purpose": PURPOSE,
            },
        )
        rows = (payload.get("items") or []) if isinstance(payload, dict) else []
        pods = {row.get("pod") for row in rows if isinstance(row, dict)}
        where = f"grid operator's dataset-api mock at {plane}"
        if status != 200 or pods != expected:
            result.fail_step(
                step,
                f"the rows are not exactly the registered supply points ({where})",
                status_code=status,
                pods=sorted(p for p in pods if p),
                expected=sorted(expected),
                body=payload if status != 200 else None,
            )
            return
        result.pass_step(
            step,
            f"only the supply points registered with an admitted consent ({where})",
            pods=sorted(pods),
        )

    # ── withdrawal and what it leaves ────────────────────────────────────────

    def _relayed_withdrawal(self, result: FlowResult) -> None:
        s = self.settings
        status, body = self._share(
            s.data_subject_id, s.grid_release_offer_id, enabled=False
        )
        row = body[0] if isinstance(body, list) and body else {}
        if (
            status != 200
            or row.get("status") != "revoked"
            or row.get("decided_by") != "subject"
            or row.get("keys_supplied") is not False
        ):
            result.fail_step(
                "relayed withdrawal",
                "the member's withdrawal, relayed by the community, was not recorded "
                "as the member's with the keys dropped",
                status_code=status,
                body=body,
            )
            return
        result.pass_step(
            "relayed withdrawal",
            "the member withdrew the release through the community; the holder "
            "records it as the member's and drops the keys",
        )

    def _check_withdrawn_read_back(self, result: FlowResult) -> None:
        s = self.settings
        status, body = self._read_back(s.data_subject_id, self.collector)
        shares = {
            item.get("offer_id"): item
            for item in (body if isinstance(body, list) else [])
            if isinstance(item, dict)
        }
        use = shares.get(s.grid_use_offer_id, {})
        release = shares.get(s.grid_release_offer_id, {})
        if not (
            status == 200
            and release.get("status") == "revoked"
            and use.get("status") == "granted"
            and use.get("missing_prerequisites") == [s.grid_release_offer_id]
        ):
            result.fail_step(
                "the dependent row stands, its admission does not",
                "the use offer's row should stand and name the withdrawn release",
                shares=shares,
            )
            return
        result.pass_step(
            "the dependent row stands, its admission does not",
            "withdrawing the release withdrew the use offer's admission, not its row",
        )

    def _decisions(
        self, offer: str, headers: dict[str, str], **params: Any
    ) -> tuple[int, Any]:
        s = self.settings
        return self.http.raw(
            "GET",
            f"{s.grid_operator_connector_url}/consent/admin/decisions?"
            + urllib.parse.urlencode({"offer_id": offer, **params}),
            headers=headers,
        )

    def _all_decisions(self, offer: str, limit: int) -> tuple[int, dict[str, Any], int]:
        """Every page, joined: ``(status, {subject: decisions}, pages)``."""
        listed: dict[str, list[dict[str, Any]]] = {}
        cursor = None
        pages = 0
        while True:
            params: dict[str, Any] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor
            status, body = self._decisions(offer, self.collector, **params)
            if status != 200 or not isinstance(body, dict):
                return status, {"body": body}, pages
            pages += 1
            for entry in body.get("subjects") or []:
                if entry["subject_id"] in listed:
                    return 0, {"repeated": entry["subject_id"]}, pages
                listed[entry["subject_id"]] = entry["decisions"]
            cursor = body.get("next_cursor")
            if not cursor:
                return status, listed, pages

    def _check_decisions_list(self, result: FlowResult) -> None:
        """ADR-0021 live: the community lists its members' decisions, every
        state, bounded as the per-subject read-back is."""
        s = self.settings
        release = s.grid_release_offer_id
        step = "the list read says who withdrew"

        unlisted, body = self._decisions(release, self.consumer)
        if unlisted != 403 or "not an accepted consent collector" not in _detail(body):
            result.fail_step(
                step,
                "an organisation the registry does not list must be refused, not "
                "answered with an empty list",
                status_code=unlisted,
                body=body,
            )
            return

        status, listed, _ = self._all_decisions(release, limit=100)
        paged_status, paged, pages = self._all_decisions(release, limit=1)
        _, back = self._read_back(s.data_subject_id, self.collector)
        presented = next(
            (
                item
                for item in (back if isinstance(back, list) else [])
                if isinstance(item, dict)
                and item.get("offer_id") == release
                and item.get("status") != "pending"
            ),
            {},
        )
        member = (listed.get(s.data_subject_id) or [{}])[0]
        dual = (listed.get(s.dual_subject_id) or [{}])[0]
        problems = {
            "status": status if status != 200 else None,
            "paged": None
            if (paged_status, paged) == (200, listed)
            else {"status": paged_status, "pages": pages},
            "withdrawn member": None
            if (
                member.get("state") == "withdrawn"
                and member.get("decided_by") == "subject"
                and member.get("consent_id") == presented.get("id")
            )
            else {"listed": member, "subject-shares": presented.get("id")},
            "member still sharing": None
            if (
                dual.get("state") == "granted"
                and dual.get("keys") == [f"pod:{POD_DUAL}"]
            )
            else dual,
            "another organisation's member": s.partner_member_id
            if s.partner_member_id in listed
            else None,
        }
        wrong = {k: v for k, v in problems.items() if v is not None}
        if wrong:
            result.fail_step(
                step,
                "the list read must agree with the per-subject read-back, list "
                "every state and only the community's own members",
                wrong=wrong,
            )
            return
        result.pass_step(
            step,
            "403 for an unlisted organisation; for the community the withdrawn "
            "member is listed as withdrawn (the row subject-shares presents), the "
            "member still sharing with their keys, and no other organisation's "
            "member — the same whole list one subject per page",
            subjects=len(listed),
            pages=pages,
        )

    def _check_provenance(self, result: FlowResult) -> None:
        s = self.settings
        url = f"{s.grid_operator_provenance_url}/prov/events?" + urllib.parse.urlencode(
            {"event_type": "ConsentRevoked", "subject_id": s.data_subject_id}
        )
        deadline = time.monotonic() + PROVENANCE_WAIT_S
        events: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            status, body = self.http.raw("GET", url, headers=self.http.bearer_headers())
            graph = body.get("@graph") if isinstance(body, dict) else body
            events = [
                e
                for e in (graph or [])
                if isinstance(e, dict)
                and e.get("ds:offerId") == s.grid_release_offer_id
                and e.get("ds:collector") == s.provider_did
            ]
            if events:
                break
            time.sleep(1.0)
        leaked = [e for e in events if POD_MEMBER in str(e)]
        if not events or leaked:
            result.fail_step(
                "provenance names the collector, never the keys",
                "no ConsentRevoked naming the community at the grid operator"
                if not events
                else "a supply point reached provenance",
                url=url,
            )
            return
        event = events[0]
        if event.get("ds:decidedBy") != "subject":
            result.fail_step(
                "provenance names the collector, never the keys",
                "the relayed withdrawal is not recorded as the member's",
                event=event,
            )
            return
        result.pass_step(
            "provenance names the collector, never the keys",
            "the grid operator's provenance records the member's withdrawal, "
            "registered by the community's client",
        )

    def _check_authority(self, result: FlowResult) -> None:
        """`D-15c` live: the community, deciding for itself, may not lift it."""
        s = self.settings
        status, body = self._share(
            s.data_subject_id,
            s.grid_release_offer_id,
            enabled=True,
            decided_by="collector",
            keys=[f"pod:{POD_MEMBER}"],
        )
        if status != 409 or "withdrew this share themselves" not in _detail(body):
            result.fail_step(
                "a relayed withdrawal is the member's",
                "the community lifted the member's withdrawal on its own authority",
                status_code=status,
                body=body,
            )
            return
        result.pass_step(
            "a relayed withdrawal is the member's",
            "409: only the member (relayed as `subject`) may re-open it",
        )


def _detail(body: Any) -> str:
    return str(body.get("detail")) if isinstance(body, dict) else str(body)
