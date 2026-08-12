"""Provenance lineage — is the record actually reconstructable?

`smoke` asserts that a set of event *types* was emitted. That is a weak claim:
it proves messages arrived, not that they compose into an account of what
happened. A regulator, an auditor or a data subject asking "where did this data
come from and who received it" needs a connected graph, not a list.

This flow asserts the graph. It records an ingestion, walks the lineage of the
dataset IRI, and checks that the ingestion, its provider and the dataset are
joined by PROV relations — then that the audit log and its summary agree with
each other.

It also asserts two production properties the happy path never exercises:

- **Idempotency.** Every emitter here retries. An event replayed under the same
  id must not double-count, or the provenance record inflates itself under
  load and the audit trail stops being evidence.
- **Consent-snapshot stability.** The ingestion record fingerprints the consent
  state that authorised it. Recomputing it over unchanged consent must give the
  same hash, or the fingerprint proves nothing.
- **Disclosure carries the same fingerprint.** Data leaving the platform is
  recorded through the connector, which computes the hash itself — rulebook
  `L-2` is only enforceable because the caller cannot supply one. A disclosure
  and an ingestion over the same consent state must agree, or neither is
  recomputable.

Needs connector, provenance and identity-registry. Runs richer assertions when a
`smoke` run has already populated the store, and says so when it has not.
"""
from __future__ import annotations

import logging
import urllib.parse
import uuid
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)


class LineageFlow(BaseFlow):
    name = "lineage"
    description = (
        "Provenance graph connectivity, ingestion recording, event idempotency "
        "and audit-log consistency"
    )
    rules = ("L-5", "L-12")

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        for name, url in (("connector", s.connector_url), ("provenance", s.provenance_url)):
            try:
                self.http.get(f"{url}/health")
            except Exception as exc:
                result.fail_step("health", f"{name} unreachable: {exc}")
                return result
        result.pass_step("health", "connector and provenance reachable")

        try:
            headers = self.http.bearer_headers()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result

        event_id = f"e2e-ingestion-{uuid.uuid4().hex[:12]}"
        if not self._check_ingestion(result, headers, event_id):
            return result
        self._check_idempotency(result, headers, event_id)
        self._check_disclosure(result, headers)
        self._check_lineage(result, headers)
        self._check_audit_log(result, headers)
        return result

    # ── ingestion ────────────────────────────────────────────────────────────

    def _check_ingestion(
        self, result: FlowResult, headers: dict[str, str], event_id: str
    ) -> bool:
        """Recording a handover must fingerprint the consent that allowed it.

        The DSO leg is manual, so this endpoint is how an offline handover
        enters the record. Its value is entirely in the snapshot hash: it binds
        the handover to the consent state in force at that moment, without the
        provenance store ever holding subject data.
        """
        s = self.settings
        body = {
            "dataset_id": s.asset_id,
            "source_ref": "e2e-lineage-handover",
            "record_count": 42,
            "agreement_ref": "e2e-dpa-ref",
            "event_id": event_id,
        }
        status, payload = self.http.raw(
            "POST", f"{s.connector_url}/admin/ingestion", body=body, headers=headers
        )
        if status != 200 or not isinstance(payload, dict):
            result.fail_step(
                "ingestion recorded",
                "the ingestion handover was not recorded",
                status_code=status,
                response=payload,
            )
            return False
        snapshot = payload.get("consent_snapshot_hash")
        if not snapshot:
            result.fail_step(
                "ingestion recorded",
                "no consent snapshot hash was computed — the record does not say "
                "which consent state authorised the handover",
                response=payload,
            )
            return False

        # Recomputed over unchanged consent, the fingerprint must not move.
        _, again = self.http.raw(
            "POST",
            f"{s.connector_url}/admin/ingestion",
            body={**body, "event_id": f"{event_id}-recompute"},
            headers=headers,
        )
        if isinstance(again, dict) and again.get("consent_snapshot_hash") != snapshot:
            result.fail_step(
                "ingestion recorded",
                "the consent snapshot hash changed while the consent state did not",
                first=snapshot,
                second=again.get("consent_snapshot_hash"),
            )
            return False
        result.pass_step(
            "ingestion recorded",
            "the handover is recorded with a stable consent-state fingerprint",
            consent_snapshot_hash=snapshot,
            granted_party_count=payload.get("granted_party_count"),
        )
        return True

    def _check_idempotency(
        self, result: FlowResult, headers: dict[str, str], event_id: str
    ) -> None:
        """A replayed event must not become a second event.

        Emitters retry on timeout; a provenance store that appends on every
        retry reports more disclosures than occurred, which is worse than
        reporting none — it is evidence that is wrong rather than absent.
        """
        s = self.settings
        before = self._count_events(headers, "DataIngested")
        self.http.raw(
            "POST",
            f"{s.connector_url}/admin/ingestion",
            body={
                "dataset_id": s.asset_id,
                "source_ref": "e2e-lineage-handover",
                "record_count": 42,
                "agreement_ref": "e2e-dpa-ref",
                "event_id": event_id,  # the same id as before
            },
            headers=headers,
        )
        after = self._count_events(headers, "DataIngested")
        if after != before:
            result.fail_step(
                "event idempotency",
                "replaying an event under the same id created a second record",
                before=before,
                after=after,
            )
            return
        result.pass_step(
            "event idempotency",
            "an event replayed under the same id is deduplicated",
            data_ingested_events=after,
        )

    # ── disclosure ───────────────────────────────────────────────────────────

    def _check_disclosure(self, result: FlowResult, headers: dict[str, str]) -> None:
        """Data leaving the platform must carry the consent state that allowed it.

        The mirror of `_check_ingestion`, and the reason rulebook `L-2` is
        enforceable at all. The caller never sends a `consent_snapshot_hash` —
        it is computed from the connector's own consent DB, which is precisely
        what the out-of-repo producer this route replaced could not do. So the
        assertion is not "the field arrived" but "the connector produced the same
        fingerprint the ingestion of that consent state produced".
        """
        s = self.settings
        status, payload = self.http.raw(
            "POST",
            f"{s.connector_url}/admin/disclosure",
            body={
                "dataset_id": s.asset_id,
                "recipient_ref": "e2e-recipient",
                "purpose": ["GridMonitoring"],
                "columns": ["pod_code", "consumption"],
                "subject_count": 1,
                "source_ref": "e2e-lineage-export",
                "agreement_ref": "e2e-dpa-ref",
                "event_id": f"e2e-disclosure-{uuid.uuid4().hex[:12]}",
            },
            headers=headers,
        )
        if status != 200 or not isinstance(payload, dict):
            result.fail_step(
                "disclosure recorded",
                "the disclosure was not recorded",
                status_code=status,
                response=payload,
            )
            return

        snapshot = payload.get("consent_snapshot_hash")
        if not snapshot:
            result.fail_step(
                "disclosure recorded",
                "no consent snapshot hash was computed — the record does not say "
                "which consent state authorised the handover (L-2)",
                response=payload,
            )
            return

        # The same consent state, so the same fingerprint the ingestion got. A
        # hash that differs per call proves nothing by recomputation.
        _, ingested = self.http.raw(
            "POST",
            f"{s.connector_url}/admin/ingestion",
            body={
                "dataset_id": s.asset_id,
                "source_ref": "e2e-lineage-handover",
                "record_count": 42,
                "agreement_ref": "e2e-dpa-ref",
                "event_id": f"e2e-ingestion-recheck-{uuid.uuid4().hex[:12]}",
            },
            headers=headers,
        )
        if isinstance(ingested, dict) and ingested.get("consent_snapshot_hash") != snapshot:
            result.fail_step(
                "disclosure recorded",
                "the disclosure and the ingestion fingerprinted the same consent "
                "state differently — neither is recomputable",
                disclosure=snapshot,
                ingestion=ingested.get("consent_snapshot_hash"),
            )
            return

        result.pass_step(
            "disclosure recorded",
            "the disclosure carries the consent-state fingerprint the connector "
            "computed, not one the caller supplied",
            consent_snapshot_hash=snapshot,
            granted_party_count=payload.get("granted_party_count"),
        )

    # ── lineage graph ────────────────────────────────────────────────────────

    def _check_lineage(self, result: FlowResult, headers: dict[str, str]) -> None:
        """The dataset must be reachable from what produced it.

        The ingestion above generated the dataset entity, so an upstream walk
        from the dataset IRI has to arrive at that activity. If it does not, the
        events were stored but never joined — a list of receipts, not a lineage.
        """
        s = self.settings
        iri = urllib.parse.quote(s.asset_id, safe="")
        status, graph = self.http.raw(
            "GET",
            f"{s.provenance_url}/prov/lineage/{iri}?direction=upstream&max_depth=5",
            headers=headers,
        )
        if status != 200 or not isinstance(graph, dict):
            result.fail_step(
                "lineage graph",
                "the dataset has no lineage — nothing links it to what produced it",
                dataset=s.asset_id,
                status_code=status,
            )
            return
        nodes = graph.get("@graph") or []
        if not isinstance(nodes, list) or len(nodes) < 2:
            result.fail_step(
                "lineage graph",
                "the lineage contains the dataset alone — no producing activity is linked",
                nodes=len(nodes) if isinstance(nodes, list) else 0,
            )
            return

        activities = [n for n in nodes if isinstance(n, dict) and self._is_activity(n)]
        if not activities:
            result.fail_step(
                "lineage graph",
                "no prov:Activity is reachable from the dataset",
                node_types=sorted({str(n.get("@type")) for n in nodes if isinstance(n, dict)}),
            )
            return
        if graph.get("root") != s.asset_id:
            result.fail_step(
                "lineage graph",
                "the graph is not rooted at the dataset it was requested for",
                requested=s.asset_id,
                root=graph.get("root"),
            )
            return
        result.pass_step(
            "lineage graph",
            "the dataset is connected upstream to the activities that produced it",
            nodes=len(nodes),
            activities=len(activities),
            depth=graph.get("depth"),
        )

        # Depth is a bound, not a suggestion: an unbounded walk over a dense
        # graph is a denial-of-service against our own API.
        _, shallow = self.http.raw(
            "GET",
            f"{s.provenance_url}/prov/lineage/{iri}?direction=upstream&max_depth=1",
            headers=headers,
        )
        if isinstance(shallow, dict) and (shallow.get("depth") or 0) > 1:
            result.fail_step(
                "lineage depth bound",
                "max_depth was exceeded — the traversal is not bounded",
                requested=1,
                returned=shallow.get("depth"),
            )
            return
        result.pass_step("lineage depth bound", "max_depth bounds the traversal")

    # ── audit log ────────────────────────────────────────────────────────────

    def _check_audit_log(self, result: FlowResult, headers: dict[str, str]) -> None:
        """The log and its summary must describe the same events.

        The summary exists so an auditor does not have to page the whole log.
        If the two disagree, the cheap view is the one people will read and the
        one that is wrong.
        """
        s = self.settings
        query = urllib.parse.urlencode({"dataset_id": s.asset_id, "limit": 500})
        status, entries = self.http.raw(
            "GET", f"{s.provenance_url}/audit/log?{query}", headers=headers
        )
        if status != 200 or not isinstance(entries, list):
            result.fail_step(
                "audit log", "the audit log is not queryable", status_code=status
            )
            return

        if not entries:
            result.pass_step(
                "audit log",
                "the audit log is queryable but empty — run `smoke` first to assert "
                "disclosure entries",
                dataset=s.asset_id,
            )
            return

        foreign = [e for e in entries if e.get("dataset_id") not in (None, s.asset_id)]
        if foreign:
            result.fail_step(
                "audit log",
                "the dataset filter returned entries for other datasets",
                foreign=[e.get("dataset_id") for e in foreign][:5],
            )
            return

        summary_query = urllib.parse.urlencode({"dataset_id": s.asset_id})
        status, summary = self.http.raw(
            "GET", f"{s.provenance_url}/audit/log/summary?{summary_query}", headers=headers
        )
        if status != 200 or not isinstance(summary, dict):
            result.fail_step(
                "audit log", "the audit summary is not available", status_code=status
            )
            return

        # `total_queries` — the field `AccessLogSummary` actually declares
        # (`provenance/schemas/audit.py`), set from `len(entries)` in
        # `api/v1/audit.py`.
        #
        # This read `total`, then `total_accesses`, then `count` (`E2E-04`).
        # Provenance has never emitted any of the three, so `total` was always
        # `None`, the `isinstance(total, int)` guard was always False, and the
        # summary-versus-log comparison — the entire point of the step — could
        # not fire. It then passed, reporting `summary_total=None`.
        #
        # Three candidate names and no assertion that one of them was found is
        # the shape to avoid: a missing key must be a failure, not a fallback to
        # the next guess.
        if "total_queries" not in summary:
            result.fail_step(
                "audit log",
                "the audit summary carries no 'total_queries' — provenance's "
                "AccessLogSummary shape has changed",
                summary_keys=sorted(summary),
            )
            return
        total = summary["total_queries"]
        if total != len(entries):
            result.fail_step(
                "audit log",
                "the summary and the log disagree on how many accesses occurred",
                summary_total=total,
                log_entries=len(entries),
            )
            return
        result.pass_step(
            "audit log",
            "the audit log filters by dataset and agrees with its summary",
            entries=len(entries),
            summary_total=total,
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _count_events(self, headers: dict[str, str], event_type: str) -> int:
        s = self.settings
        query = urllib.parse.urlencode({"event_type": event_type, "limit": 500})
        payload = self.http.get(
            f"{s.provenance_url}/prov/events?{query}", headers=headers
        ) or {}
        graph = payload.get("@graph") or []
        return len([g for g in graph if isinstance(g, dict)])

    def _is_activity(self, node: dict[str, Any]) -> bool:
        node_type = node.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        return any("Activity" in str(t) for t in types)
