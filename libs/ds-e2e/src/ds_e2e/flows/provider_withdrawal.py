"""The sync withdraws what governance no longer declares — over the wire.

**The defect.** `POST /provider/sync` created and updated; it never removed. A
dataset taken out of `governance.yaml` kept its EDC asset, both its policies and
its contract definition, and went on being offered over DSP — while the next sync
reported a publish count that had gone *up*, because the count is of what
published rather than of what is on offer. Nothing distinguished it from a
healthy run. Measured in a live deployment on 2026-09-18.

**Why this flow exists on top of the unit tests.** The unit tests drive a
stateful stand-in for EDC; this drives a real EDC through a real connector, which
is where the only thing that can be wrong is the part neither the stand-in nor
the connector knows: whether EDC accepts the delete order ds sends
(`test_the_withdrawal_order_is_the_only_one_edc_accepts` asserts ds's *intent*;
only an EDC can confirm it), and whether the asset really leaves the catalogue
rather than merely leaving ds's list of it.

**How it makes governance change without a restart.** The connector's governance
is mounted read-only, so the file cannot be edited. `POST /provider/sync` accepts
a `governance_yaml_path`, and a second file that declares **no** dataset is
mounted beside the real one (`/governance-probe`,
`services/connector/e2e-governance-probe/`). Syncing against it is the
same statement a producer makes by deleting a dataset, taken to its extreme, and
the extreme is what makes the fixture cheap: a subset file would have to be kept
in step with the real governance for ever.

Most of the catalogue is off offer between the two syncs, so the restore is in
`cleanup()` as well as in `execute`; `runner.run_flow` calls it in a `finally`.

**It must run before any negotiating flow**, and that is a requirement rather
than an ordering preference: EDC refuses to delete an asset a counterparty has
negotiated for, so after `uc1` almost everything is under agreement and the only
thing this can observe is the refusal. Which is why its central assertion is the
*rule* rather than a count — **every published asset is either withdrawn or named
in `errors`** — with at least one actually withdrawn, so the flow cannot pass by
observing nothing.

It publishes with **`svc-ds-publisher`**, not the harness client: the harness no
longer holds `connector.provider.write` (plan item 7), which is what makes "who
may publish" a question this suite can ask at all.
"""

from __future__ import annotations

import logging
import time
import urllib.parse

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

#: The sync awaits the provenance POST inline, so the event is written before the
#: sync answers. Polled anyway, briefly: emission is non-fatal by design, and a
#: flow that asserted once would turn a slow store into a false regression.
PROVENANCE_WAIT_S = 15.0


class ProviderWithdrawalFlow(BaseFlow):
    name = "provider-withdrawal"
    description = (
        "A dataset removed from governance is removed from EDC — asset, "
        "policies and contract definition — and the sync says what it withdrew"
    )
    rules = ("C-7", "L-1", "L-15")

    def _withdrawal_events(self, asset_id: str) -> list[dict]:
        """`CatalogueWithdrawn` events naming this asset, as the graph has them.

        Read with the **harness** client, not the publisher: `svc-ds-e2e` holds
        `provenance.read` and `svc-ds-publisher` holds neither provenance grant.
        Since 2026-09-20 that distinction bites — `provenance.write` no longer
        satisfies a read, so a flow reading the graph must hold the read scope
        rather than any provenance scope.
        """
        query = urllib.parse.urlencode(
            {"event_type": "CatalogueWithdrawn", "dataset_id": asset_id}
        )
        body = self.http.get(
            f"{self.settings.provenance_url}/prov/events?{query}",
            headers=self.http.bearer_headers(),
        )
        graph = body.get("@graph") if isinstance(body, dict) else body
        return [item for item in (graph or []) if isinstance(item, dict)]

    def _asset_ids(self, headers: dict[str, str]) -> set[str]:
        body = self.http.get(
            f"{self.settings.connector_url}/provider/assets", headers=headers
        )
        rows = body if isinstance(body, list) else (body or {}).get("assets") or []
        return {
            str(row.get("@id") or row.get("id"))
            for row in rows
            if isinstance(row, dict) and (row.get("@id") or row.get("id"))
        }

    def _sync(self, headers: dict[str, str], governance_path: str | None = None):
        payload = {"governance_yaml_path": governance_path} if governance_path else {}
        return (
            self.http.post(
                f"{self.settings.connector_url}/provider/sync", payload, headers=headers
            )
            or {}
        )

    def execute(self) -> FlowResult:
        result = FlowResult(flow_name=self.name)
        if not self._check_health(result):
            return result

        try:
            headers = self.http.publisher_headers()
            result.pass_step(
                "publisher token",
                "svc-ds-publisher authenticated — two grants, no management-api:*",
            )
        except Exception as exc:
            result.fail_step("publisher token", str(exc))
            return result

        # 1. The catalogue as governance declares it.
        try:
            published = self._sync(headers)
            before = self._asset_ids(headers)
        except Exception as exc:
            result.fail_step("baseline sync", str(exc))
            return result
        if not before:
            result.fail_step(
                "baseline sync",
                "the provider published nothing, so there is nothing to withdraw",
                errors=published.get("errors"),
            )
            return result
        result.pass_step(
            "baseline sync",
            "the provider's governance is published",
            assets=len(before),
        )

        # 2. The same connector, governance that declares nothing.
        try:
            withdrawn_result = self._sync(headers, self.settings.withdrawal_probe_path)
        except Exception as exc:
            result.fail_step("withdrawing sync", str(exc))
            return result

        withdrawn = set(withdrawn_result.get("withdrawn") or [])
        errors = withdrawn_result.get("errors") or []
        # By **asset id**: `before` is a set of asset ids, and the key and the id
        # coincide only where the id is unset or pinned to the key. The sync
        # reports both for exactly this reason.
        refused = {
            e.get("asset") for e in errors if isinstance(e, dict) and e.get("asset")
        }

        # **Every published asset is accounted for, one way or the other.** An
        # asset EDC refuses to delete because a counterparty has negotiated for it
        # (409) is a real and correct outcome — and it has to be *reported*, not
        # swallowed, because a dataset that governance has dropped and DSP is
        # still offering is exactly the state an operator must be told about. What
        # must never happen is an asset that is neither withdrawn nor named.
        unaccounted = before - withdrawn - refused
        if unaccounted:
            result.fail_step(
                "every published asset is accounted for",
                "governance declared no dataset, and these were neither withdrawn "
                "nor reported — this is the defect: creation was owned, removal "
                "was not",
                assets=sorted(unaccounted),
                result=withdrawn_result,
            )
            return result
        if not withdrawn:
            result.fail_step(
                "every published asset is accounted for",
                "nothing was withdrawn at all. If every asset is under a contract "
                "agreement this flow cannot prove anything — run it before the "
                "negotiating flows, or after `ds-e2e clean`",
                refused=sorted(refused),
            )
            return result
        result.pass_step(
            "every published asset is accounted for",
            "each one was withdrawn, or named as refused by EDC",
            withdrawn=sorted(withdrawn),
            refused_by_edc=sorted(refused),
        )

        # 3. EDC, asked directly. The report is not the catalogue.
        try:
            after = self._asset_ids(headers)
        except Exception as exc:
            result.fail_step("EDC no longer holds them", str(exc))
            return result
        still_there = withdrawn & after
        if still_there:
            result.fail_step(
                "EDC no longer holds them",
                "the sync said it withdrew these and EDC still serves them — "
                "they are still on offer over DSP",
                assets=sorted(still_there),
            )
            return result
        result.pass_step(
            "EDC no longer holds them",
            "what the sync reported withdrawn is gone at the EDC, not merely "
            "gone from the report",
            remaining=len(after),
        )

        # 4. The graph says so too. Until 2026-09-20 a dataset came off offer and
        #    left no trace, so provenance's last word on it was its publication —
        #    a record that is wrong rather than merely short (ADR-0017's
        #    amendment). Every asset withdrawn here is withdrawn because the probe
        #    governance declares nothing, which is the `undeclared` case and the
        #    only one that emits.
        deadline = time.monotonic() + PROVENANCE_WAIT_S
        unrecorded = sorted(withdrawn)
        try:
            while time.monotonic() < deadline:
                unrecorded = sorted(
                    asset for asset in withdrawn if not self._withdrawal_events(asset)
                )
                if not unrecorded:
                    break
                time.sleep(1.0)
        except Exception as exc:
            result.fail_step("the withdrawal is in the graph", str(exc))
            return result
        if unrecorded:
            result.fail_step(
                "the withdrawal is in the graph",
                "these assets were withdrawn at the EDC and no CatalogueWithdrawn "
                "names them — the graph still says they are published",
                assets=unrecorded,
            )
            return result
        result.pass_step(
            "the withdrawal is in the graph",
            "every withdrawn asset has a CatalogueWithdrawn event of its own",
            assets=sorted(withdrawn),
        )

        # 5. Restored in the same run, so this is a cycle rather than a one-way
        #    door. `cleanup()` repeats it on the exception path.
        try:
            self._sync(headers)
            restored = self._asset_ids(headers)
        except Exception as exc:
            result.fail_step("restored", str(exc))
            return result
        missing = before - restored
        if missing:
            result.fail_step(
                "restored",
                "re-syncing the real governance did not bring every asset back",
                missing=sorted(missing),
            )
            return result
        result.pass_step(
            "restored",
            "the catalogue is back to what governance declares",
            assets=len(restored),
        )
        return result

    def cleanup(self) -> None:
        """Republish the connector's own governance, whatever happened above.

        Idempotent and cheap. Without it, an exception between the withdrawing
        sync and the restore would leave every later flow negotiating for assets
        that are not there — a failure with no visible relation to its cause.
        """
        try:
            self._sync(self.http.publisher_headers())
        except Exception as exc:  # noqa: BLE001 — cleanup must not mask the failure
            log.warning("provider-withdrawal cleanup could not re-sync: %s", exc)
