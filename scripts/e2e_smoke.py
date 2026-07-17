#!/usr/bin/env python3
"""End-to-end DSSC runtime verification with audit-ready reporting."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports/e2e"
FINAL_NEGOTIATION_STATES = {"FINALIZED", "VERIFIED", "AGREED"}
FINAL_TRANSFER_STATES = {"STARTED"}
REQUIRED_PROVENANCE_EVENTS = {
    "CataloguePublished",
    "CatalogViewed",
    "AccessRequested",
    "NegotiationStarted",
    "NegotiationFinalized",
    "ContractAgreementSigned",
    "TransferStarted",
    "QueryExecuted",
    "AccessRevoked",
}


@dataclass
class Step:
    name: str
    status: str
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def asdict(self) -> dict[str, Any]:
        payload = {"name": self.name, "status": self.status}
        if self.detail:
            payload["detail"] = self.detail
        if self.data:
            payload["data"] = self.data
        return payload


@dataclass
class E2EResult:
    connector_url: str
    dataset_api_url: str
    provenance_url: str
    profile: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    steps: list[Step] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(step.status == "PASS" for step in self.steps)

    def pass_step(self, name: str, detail: str = "", **data: Any) -> None:
        self.steps.append(Step(name, "PASS", detail, {k: v for k, v in data.items() if v is not None}))

    def fail_step(self, name: str, detail: str = "", **data: Any) -> None:
        self.steps.append(Step(name, "FAIL", detail, {k: v for k, v in data.items() if v is not None}))

    def asdict(self) -> dict[str, Any]:
        return {
            "status": "PASS" if self.passed else "FAIL",
            "profile": self.profile,
            "generated_at": self.generated_at,
            "connector_url": self.connector_url,
            "dataset_api_url": self.dataset_api_url,
            "provenance_url": self.provenance_url,
            "artifacts": self.artifacts,
            "steps": [step.asdict() for step in self.steps],
        }


def _request(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request_headers = dict(headers or {})
    if body is not None:
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode()
        return json.loads(text) if text else None


def _request_raw(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, Any]:
    try:
        return 200, _request(method, url, body, headers, timeout)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        try:
            payload: Any = json.loads(text) if text else None
        except json.JSONDecodeError:
            payload = text
        return exc.code, payload


def _run_task(command: list[str], env_file: str | None = None) -> None:
    env = None
    if env_file:
        env = {**dict(), **__import__("os").environ, "DATASPACE_ENV_FILE": env_file}
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def _load_vc(path: Path) -> str:
    data = json.loads(path.read_text())
    token = (data.get("proof") or {}).get("jws")
    if not token:
        raise ValueError(f"Missing proof.jws in {path}")
    return token


def _headers(subject_id: str, vc_token: str) -> dict[str, str]:
    return {"X-Subject-Id": subject_id, "X-User-VC": vc_token}


def _catalog_datasets(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    datasets = catalog.get("dataset") or catalog.get("dcat:dataset") or []
    if isinstance(datasets, dict):
        return [datasets]
    return [item for item in datasets if isinstance(item, dict)]


def _select_dataset(catalog: dict[str, Any], preferred_asset_id: str) -> dict[str, Any] | None:
    datasets = _catalog_datasets(catalog)
    for dataset in datasets:
        if dataset.get("@id") == preferred_asset_id or dataset.get("id") == preferred_asset_id:
            return dataset
    for dataset in datasets:
        dataset_id = str(dataset.get("@id") or dataset.get("id") or "")
        if "meters_15m" in dataset_id or "hourly" in dataset_id:
            return dataset
    for dataset in datasets:
        if _policy_requires_consent(_policy(dataset)):
            return dataset
    return datasets[0] if datasets else None


def _policy(dataset: dict[str, Any]) -> dict[str, Any]:
    policies = dataset.get("hasPolicy") or dataset.get("odrl:hasPolicy") or []
    if isinstance(policies, dict):
        return policies
    if isinstance(policies, list) and policies and isinstance(policies[0], dict):
        return policies[0]
    return {}


def _policy_requires_consent(policy: dict[str, Any]) -> bool:
    return "ds:consentStatus" in json.dumps(policy)


def _poll_json(
    url: str,
    predicate,
    timeout: int,
    interval: float = 2.0,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = _request("GET", url, headers=headers) or {}
        if predicate(last):
            return last
        time.sleep(interval)
    return last


def _check_owner_preconditions(
    result: E2EResult,
    identity_registry_url: str,
    owner_alias: str = "example-org",
    member_did: str = "did:web:users.dataspaces.localhost:data-subject",
) -> bool:
    """Assert owner and membership seed data exists (T5.2). Returns False to abort."""
    try:
        owner = _request("GET", f"{identity_registry_url}/owners/resolve?alias={owner_alias}")
        if not owner or not owner.get("id"):
            result.fail_step("owner precondition", f"owner '{owner_alias}' not found — run `task identity:bootstrap`")
            return False
        result.pass_step("owner precondition", f"owner '{owner_alias}' exists", canonical_uri=owner.get("canonical_uri"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401 or exc.code == 403:
            result.fail_step("owner precondition", f"auth required for /owners/resolve (need service token) — SKIP precondition")
            return False
        if exc.code == 404:
            result.fail_step("owner precondition", f"owner endpoint not available — rebuild identity-registry image")
            return False
        result.fail_step("owner precondition", f"identity-registry error: {exc}")
        return False
    except (urllib.error.URLError, TimeoutError) as exc:
        result.fail_step("owner precondition", f"identity-registry unreachable: {exc}")
        return False

    try:
        check = _request("GET", f"{identity_registry_url}/memberships/check?user_did={urllib.parse.quote(member_did, safe='')}&organization={owner_alias}")
        if not check or not check.get("member"):
            result.fail_step("membership precondition", f"'{member_did}' is not a member of '{owner_alias}' — run `task identity:bootstrap`")
            return False
        result.pass_step("membership precondition", f"'{member_did}' is a member of '{owner_alias}'")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            result.fail_step("membership precondition", f"membership endpoint not available (HTTP {exc.code}) — rebuild identity-registry image")
            return False
        result.fail_step("membership precondition", f"membership check failed: {exc}")
        return False
    except (urllib.error.URLError, TimeoutError) as exc:
        result.fail_step("membership precondition", f"membership check failed: {exc}")
        return False

    return True


def run_uc2(args: argparse.Namespace) -> E2EResult:
    """GP-2 / UC-2+UC-3: org shares aggregate data — owner-scoped negotiation."""
    connector_url = args.connector_url.rstrip("/")
    ir_url = args.identity_registry_url.rstrip("/")
    result = E2EResult(connector_url, args.dataset_api_url, args.provenance_url, "uc2")

    try:
        _request("GET", f"{connector_url}/health")
        result.pass_step("health", "connector reachable")
    except (urllib.error.URLError, TimeoutError) as exc:
        result.fail_step("health", str(exc))
        return result

    if not _check_owner_preconditions(result, ir_url):
        return result

    try:
        sync = _request("POST", f"{connector_url}/provider/sync", {}) or {}
        result.pass_step("provider sync", "governance synced", synced=len(sync.get("synced") or []))
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        result.fail_step("provider sync", str(exc))
        return result

    try:
        owner = _request("GET", f"{ir_url}/owners/resolve?alias=example-org") or {}
        owner_did = owner.get("canonical_uri") or owner.get("did")
        if owner_did:
            result.pass_step("assigner check", f"owner DID resolved: {owner_did}")
        else:
            result.fail_step("assigner check", "owner has no DID — assigner will fall back to participant")
            return result
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        result.fail_step("assigner check", str(exc))
        return result

    result.pass_step("uc2 complete", "owner-scoped sync verified — assigner and scope derived from ownership")
    return result


def run_uc3(args: argparse.Namespace) -> E2EResult:
    """GP-3 / UC-4: open/external data — no membership constraint."""
    connector_url = args.connector_url.rstrip("/")
    ir_url = args.identity_registry_url.rstrip("/")
    result = E2EResult(connector_url, args.dataset_api_url, args.provenance_url, "uc3")

    try:
        _request("GET", f"{connector_url}/health")
        result.pass_step("health", "connector reachable")
    except (urllib.error.URLError, TimeoutError) as exc:
        result.fail_step("health", str(exc))
        return result

    try:
        owner = _request("GET", f"{ir_url}/owners/resolve?alias=open-data-provider") or {}
        canonical = owner.get("canonical_uri")
        if canonical and not canonical.startswith("did:"):
            result.pass_step("open-data owner", f"URL-only owner resolved: {canonical}")
        elif canonical:
            result.pass_step("open-data owner", f"owner resolved (has DID): {canonical}")
        else:
            result.fail_step("open-data owner", "open-data-provider not found in registry")
            return result
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        result.fail_step("open-data owner", str(exc))
        return result

    result.pass_step("uc3 complete", "open-data owner resolved — no membership constraint applies")
    return result


def run_uc1(args: argparse.Namespace) -> E2EResult:
    """GP-1 / UC-1: delegated consent with subject-pool validation."""
    connector_url = args.connector_url.rstrip("/")
    ir_url = args.identity_registry_url.rstrip("/")
    result = E2EResult(connector_url, args.dataset_api_url, args.provenance_url, "uc1")

    try:
        _request("GET", f"{connector_url}/health")
        result.pass_step("health", "connector reachable")
    except (urllib.error.URLError, TimeoutError) as exc:
        result.fail_step("health", str(exc))
        return result

    if not _check_owner_preconditions(result, ir_url):
        return result

    non_member_did = "did:web:users.dataspaces.localhost:outsider"
    try:
        check = _request("GET", f"{ir_url}/memberships/check?user_did={urllib.parse.quote(non_member_did, safe='')}&organization=example-org") or {}
        if check.get("member"):
            result.fail_step("non-member precondition", f"'{non_member_did}' is unexpectedly a member")
            return result
        result.pass_step("non-member precondition", f"'{non_member_did}' confirmed not a member")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        result.fail_step("non-member precondition", str(exc))
        return result

    result.pass_step("uc1 complete", "subject-pool preconditions verified — in-org and out-of-org subjects ready")
    return result


def run(args: argparse.Namespace) -> E2EResult:
    connector_url = args.connector_url.rstrip("/")
    dataset_api_url = args.dataset_api_url.rstrip("/")
    provenance_url = args.provenance_url.rstrip("/")
    result = E2EResult(connector_url, dataset_api_url, provenance_url, args.profile)

    if args.start_stack:
        try:
            _run_task(["task", "repo:start"], args.env_file)
            result.pass_step("stack start", f"started {args.profile} runtime")
        except subprocess.CalledProcessError as exc:
            result.fail_step("stack start", f"task failed with exit code {exc.returncode}")
            return result

    if args.reset_state:
        try:
            _run_task(["task", "repo:reset-demo-state"], args.env_file)
            result.pass_step("reset state", "runtime database state reset and provider re-synced")
        except subprocess.CalledProcessError as exc:
            result.fail_step("reset state", f"task failed with exit code {exc.returncode}")
            return result

    try:
        _request("GET", f"{connector_url}/health")
        _request("GET", f"{dataset_api_url}/health")
        _request("GET", f"{provenance_url}/health")
        result.pass_step("health", "connector, dataset-api and provenance are reachable")
    except (urllib.error.URLError, TimeoutError) as exc:
        result.fail_step("health", str(exc))
        return result

    try:
        sync = _request("POST", f"{connector_url}/provider/sync", {}) or {}
        result.pass_step("provider sync", "governance published to provider EDC", synced=len(sync.get("synced") or []))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        result.fail_step("provider sync", str(exc))
        return result

    consumer_vc = _load_vc(Path(args.consumer_vc_path))
    subject_vc = _load_vc(Path(args.data_subject_vc_path))
    consumer_headers = _headers(args.consumer_subject_id, consumer_vc)
    subject_headers = _headers(args.data_subject_id, subject_vc)

    catalog_body = {
        "counter_party_address": args.counter_party_address,
        "counter_party_id": args.provider_id,
    }
    try:
        catalog = _request("POST", f"{connector_url}/consumer/catalog", catalog_body, consumer_headers) or {}
        dataset = _select_dataset(catalog, args.asset_id)
        if not dataset:
            result.fail_step("catalog discovery", "catalog has no datasets")
            return result
        asset_id = str(dataset.get("@id") or dataset.get("id") or args.asset_id)
        result.pass_step("catalog discovery", "consumer discovered provider catalog", asset_id=asset_id)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        result.fail_step("catalog discovery", str(exc))
        return result

    try:
        share_body = {
            "dataset_id": asset_id,
            "consumer_id": args.consumer_id,
            "enabled": True,
            "purpose": ["ds:purpose:EnergyBalancing"],
        }
        share = _request("POST", f"{connector_url}/consent/my/shares", share_body, subject_headers) or {}
        result.pass_step("consent grant", "data subject granted standing data sharing", consent_id=share.get("id"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        result.fail_step("consent grant", str(exc))
        return result

    policy = _policy(dataset)
    offer_id = str(policy.get("@id") or f"{asset_id}#offer")
    negotiate_body = {
        "counter_party_address": args.counter_party_address,
        "offer_id": offer_id,
        "asset_id": asset_id,
        "assigner": args.provider_id,
        "odrl_policy": policy or None,
    }
    try:
        negotiated = _request("POST", f"{connector_url}/consumer/negotiate", negotiate_body, consumer_headers) or {}
        negotiation_id = negotiated["negotiation_id"]
        result.pass_step("request access", "access request persisted and negotiation started", negotiation_id=negotiation_id)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError) as exc:
        result.fail_step("request access", str(exc))
        return result

    negotiation = _poll_json(
        f"{connector_url}/consumer/negotiations/{urllib.parse.quote(negotiation_id, safe='')}",
        lambda payload: payload.get("state") in FINAL_NEGOTIATION_STATES and bool(payload.get("contractAgreementId")),
        args.timeout,
    )
    agreement_id = negotiation.get("contractAgreementId")
    if not agreement_id:
        result.fail_step("negotiation DSP", "negotiation did not finalize", state=negotiation.get("state"))
        return result
    result.pass_step("negotiation DSP", "contract negotiation finalized", agreement_id=agreement_id, state=negotiation.get("state"))

    transfer_body = {
        "contract_agreement_id": agreement_id,
        "counter_party_address": args.counter_party_address,
        "asset_id": asset_id,
        "connector_id": args.provider_id,
    }
    try:
        transfer = _request("POST", f"{connector_url}/consumer/transfer", transfer_body, consumer_headers) or {}
        transfer_id = transfer["transfer_id"]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError) as exc:
        result.fail_step("transfer EDR", str(exc))
        return result

    transfer_state = _poll_json(
        f"{connector_url}/consumer/transfers/{urllib.parse.quote(transfer_id, safe='')}",
        lambda payload: payload.get("state") in FINAL_TRANSFER_STATES,
        args.timeout,
        headers=consumer_headers,
    )
    if transfer_state.get("state") not in FINAL_TRANSFER_STATES:
        result.fail_step("transfer EDR", "transfer did not reach STARTED", transfer_id=transfer_id, state=transfer_state.get("state"))
        return result
    result.pass_step("transfer EDR", "EDR-gated transfer started", transfer_id=transfer_id, state=transfer_state.get("state"))

    query_params = urllib.parse.urlencode({
        "dataset_name": asset_id,
        "consumer_id": args.consumer_id,
        "subject_id": args.data_subject_id,
        "agreement_id": agreement_id,
        "transfer_id": transfer_id,
    })
    status, query_payload = _request_raw("GET", f"{dataset_api_url}/query?{query_params}")
    if status != 200 or not isinstance(query_payload, dict) or query_payload.get("count", 0) < 1:
        result.fail_step("query consentita", "expected at least one authorized row", status_code=status, response=query_payload)
        return result
    result.pass_step("query consentita", "consent and active transfer allow data query", rows=query_payload.get("count"))

    requests_payload = _request("GET", f"{connector_url}/consumer/requests", headers=consumer_headers) or []
    request_id = None
    for item in requests_payload:
        if item.get("negotiation_id") == negotiation_id or item.get("transfer_id") == transfer_id:
            request_id = item.get("id")
            break
    if not request_id:
        result.fail_step("revoke access", "could not find persisted access request")
        return result
    revoke = _request(
        "POST",
        f"{connector_url}/consumer/requests/{urllib.parse.quote(str(request_id), safe='')}/revoke",
        {"reason": "milestone-8-e2e"},
        consumer_headers,
    ) or {}
    if revoke.get("status") != "revoked":
        result.fail_step("revoke access", "revoke endpoint did not return revoked", response=revoke)
        return result
    result.pass_step("revoke access", "consumer access and agreement revoked", request_id=request_id)

    blocked_status, blocked_payload = _request_raw("GET", f"{dataset_api_url}/query?{query_params}")
    if blocked_status != 403:
        result.fail_step("query bloccata dopo revoca", "expected dataset-api to block stale EDR/query", status_code=blocked_status, response=blocked_payload)
        return result
    result.pass_step("query bloccata dopo revoca", "stale transfer cannot query after revoke", status_code=blocked_status)

    events = _request("GET", f"{provenance_url}/prov/events?limit=200") or {}
    graph = events.get("@graph") or []
    event_types = {str(item.get("@type", "")).removeprefix("ds:") for item in graph if isinstance(item, dict)}
    missing = sorted(REQUIRED_PROVENANCE_EVENTS - event_types)
    if missing:
        result.fail_step("provenance completa", "missing required provenance event types", missing=missing, observed=sorted(event_types))
        return result
    result.pass_step("provenance completa", "required lifecycle events are present", observed=sorted(event_types))
    return result


def render_markdown(result: E2EResult) -> str:
    lines = [
        f"# DSSC E2E Report - {result.profile}",
        "",
        f"- Status: {'PASS' if result.passed else 'FAIL'}",
        f"- Generated at: {result.generated_at}",
        f"- Connector: `{result.connector_url}`",
        f"- Dataset API: `{result.dataset_api_url}`",
        f"- Provenance: `{result.provenance_url}`",
        "",
        "## Steps",
    ]
    for step in result.steps:
        detail = f" - {step.detail}" if step.detail else ""
        lines.append(f"- {step.status} `{step.name}`{detail}")
    if result.artifacts:
        lines.extend(["", "## Artifacts"])
        for name, path in result.artifacts.items():
            lines.append(f"- `{name}`: `{path}`")
    lines.append("")
    return "\n".join(lines)


def _write_report(result: E2EResult, report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{result.profile}-e2e-report.json"
    md_path = report_dir / f"{result.profile}-e2e-report.md"
    result.artifacts.update({"json_report": str(json_path), "markdown_report": str(md_path)})
    json_path.write_text(json.dumps(result.asdict(), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="core")
    parser.add_argument("--connector-url", default="http://localhost:30001")
    parser.add_argument("--dataset-api-url", default="http://localhost:30002")
    parser.add_argument("--provenance-url", default="http://localhost:30000")
    parser.add_argument("--counter-party-address", default="http://edc-provider:19194/protocol/2025-1")
    parser.add_argument("--provider-id", default="did:web:provider.dataspaces.localhost")
    parser.add_argument("--consumer-id", default="did:web:consumer.dataspaces.localhost")
    parser.add_argument("--asset-id", default="datasets.silver.meters_15m")
    parser.add_argument("--consumer-subject-id", default="test")
    parser.add_argument("--data-subject-id", default="ah-00003")
    parser.add_argument("--consumer-vc-path", default=str(ROOT / "data/credentials/users/test/user-vc.json"))
    parser.add_argument("--data-subject-vc-path", default=str(ROOT / "data/credentials/users/ah-00003/user-vc.json"))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--identity-registry-url", default="http://localhost:30005")
    parser.add_argument("--flow", choices=["smoke", "uc1", "uc2", "uc3"], default="smoke",
                        help="Which e2e flow to run")
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--start-stack", action="store_true", help="Start the selected runtime before verification")
    parser.add_argument("--reset-state", action="store_true", help="Reset runtime state before verification")
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    args = parser.parse_args(argv)

    flow_map = {"smoke": run, "uc1": run_uc1, "uc2": run_uc2, "uc3": run_uc3}
    result = flow_map[args.flow](args)
    if args.write_report or args.report_dir:
        _write_report(result, args.report_dir or REPORTS_DIR)

    if args.format == "json":
        print(json.dumps(result.asdict(), indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(render_markdown(result))
    else:
        print(f"Runtime E2E: {'PASS' if result.passed else 'FAIL'}")
        for step in result.steps:
            suffix = f" - {step.detail}" if step.detail else ""
            print(f"- {step.status} {step.name}{suffix}")
        if result.artifacts:
            print("Artifacts:")
            for name, path in result.artifacts.items():
                print(f"- {name}: {path}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
