"""The consumer's organisation on the agreement path, asserted live.

Three flows over one exchange shape — the consumer organisation's own token
drives catalogue → negotiation → transfer → EDR → query, as `organisation-token`
does — each about what the agreement does **not** settle on its own:

- `organization-rows` (`X-17`, `X-18`): an organization-bound dataset serves the
  consumer exactly the rows of the organization its `OrganizationCredential`
  names, and a consumer whose organization does not satisfy the declared layer
  gets no rows at all;
- `layer-verdicts` (`X-19`): a person layer declared `allow_all` gates nothing
  on consent, and an organization layer declared `deny_all` refuses the query
  (`row_policy_denied`) through a live agreement;
- `organization-reissue` (`P-30`, `P-31`): `ir-cli org reissue` delivers a
  successor and suspends the predecessor on the issuer's register; the holder
  then presents the successor and never the suspended copy, and the exchange
  still works.

**Every target is a provider DID and an asset id** (`config.py`, "The consumer's
organisation on the agreement path"). The provider's DSP address and the holder's
credential service are read from the DID documents, so a target cannot name one
participant and dial another. No governance file in this repository declares an
organization-bound dataset or a `deny_all` layer, so the defaults are empty and a
flow with nothing to target **skips, and says which setting it is missing** —
declared before any check, never in place of one that failed.

**What the flows cannot see, and do not claim.** The provider's verdict
(`organizations`, the reason it is empty) travels from the connector to the data
plane, not to the consumer. So the assertions are on what the consumer receives:
the rows' own organization column, an empty answer, a refusal naming its reason.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
import shlex
import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from ds_e2e.flows.base import BaseFlow
from ds_e2e.flows.dcp_trust import _did_web_url, _participant_base, decode_encoded_list
from ds_e2e.flows.organisation_token import EDC_TOKEN_SCOPE
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

FINAL_NEGOTIATION_STATES = {"FINALIZED", "VERIFIED", "AGREED"}
#: The request every flow here files its exchanges under, so each one revokes
#: exactly its own on the way in and out.
REASON = "e2e-organization-layer"
#: The DCP scope a verifier asks for when it wants the organisation credential.
ORGANIZATION_SCOPE = "org.eclipse.dspace.dcp.vc.type:OrganizationCredential:read"
QUERY_LIMIT = 1000


# ── reading credentials ─────────────────────────────────────────────────────


def _jwt_claims(token: str) -> dict[str, Any]:
    """A JWS's payload, unverified: the verifier's EDC verifies, this reads."""
    try:
        segment = token.split(".")[1]
        claims: dict[str, Any] = json.loads(
            base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        )
        return claims
    except (IndexError, ValueError):
        return {}


@dataclass(frozen=True)
class PresentedCredential:
    id: str
    types: tuple[str, ...]
    organization_id: str | None
    #: `statusPurpose` → (list URL, index), as the credential names them.
    status: dict[str, tuple[str, int]] = field(default_factory=dict)


def presented_credentials(response: Any) -> list[PresentedCredential]:
    """Every credential inside a DCP `PresentationResponseMessage`.

    Reads both spellings the response takes — `presentation` and the compacted
    `dcp:presentation` holding its list under `@value` — and both credential
    forms, a JWT and an embedded object.
    """
    if not isinstance(response, dict):
        return []
    raw = response.get("presentation") or response.get("dcp:presentation") or []
    if isinstance(raw, dict):
        raw = raw.get("@value") or []
    if not isinstance(raw, list):
        raw = [raw]
    found: list[PresentedCredential] = []
    for vp in raw:
        claims = _jwt_claims(vp) if isinstance(vp, str) else vp
        if not isinstance(claims, dict):
            continue
        body = claims.get("vp") or claims
        credentials = body.get("verifiableCredential") or []
        if not isinstance(credentials, list):
            credentials = [credentials]
        for item in credentials:
            vc = _jwt_claims(item) if isinstance(item, str) else item
            if not isinstance(vc, dict):
                continue
            vc = vc.get("vc") or vc
            subject = vc.get("credentialSubject") or {}
            if isinstance(subject, list):
                subject = subject[0] if subject else {}
            entries = vc.get("credentialStatus") or []
            if isinstance(entries, dict):
                entries = [entries]
            status: dict[str, tuple[str, int]] = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    status[str(entry.get("statusPurpose"))] = (
                        str(entry["statusListCredential"]),
                        int(entry["statusListIndex"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            types = vc.get("type") or []
            found.append(
                PresentedCredential(
                    id=str(vc.get("id") or ""),
                    types=tuple(types if isinstance(types, list) else [types]),
                    organization_id=(
                        subject.get("organizationId")
                        if isinstance(subject, dict)
                        else None
                    ),
                    status=status,
                )
            )
    return found


def status_bit(encoded_list: str, index: int) -> bool:
    """Bit `index` of a Bitstring Status List's `encodedList`, MSB first."""
    raw = gzip.decompress(decode_encoded_list(encoded_list))
    return bool(raw[index // 8] & (1 << (7 - index % 8)))


def parse_reissue(output: str) -> dict[str, Any]:
    """What `ir-cli org reissue` printed: the successor, delivery, suspensions."""
    issued: str | None = None
    delivered = False
    suspended: list[str] = []
    errors: list[str] = []
    for line in output.splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == "issued" and len(words) > 1:
            issued = words[1]
        elif words[0] == "delivered":
            delivered = True
        elif words[0] == "suspended" and len(words) > 1:
            suspended.append(words[1])
        elif words[0] == "ERROR":
            errors.append(line.strip())
    return {
        "issued": issued,
        "delivered": delivered,
        "suspended": suspended,
        "errors": errors,
    }


# ── the exchange ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Exchange:
    asset_id: str
    agreement_id: str
    transfer_id: str
    token: str
    endpoint: str
    purpose: str
    policy: dict[str, Any]


class _AgreementPathFlow(BaseFlow):
    """Catalogue → negotiation → transfer → EDR for one target, then queries."""

    #: The assets this flow negotiates for, revoked in `cleanup`.
    def _assets(self) -> list[str]:
        return []

    def cleanup(self) -> None:
        try:
            headers = self._headers()
        except Exception:
            return
        for asset_id in self._assets():
            if asset_id:
                self._revoke_own(headers, asset_id)

    def _headers(self) -> dict[str, str]:
        s = self.settings
        return self.http.bearer_headers_for(
            s.consumer_org_client_id, s.consumer_org_client_secret, EDC_TOKEN_SCOPE
        )

    def _authenticate(self, result: FlowResult) -> dict[str, str] | None:
        s = self.settings
        try:
            headers = self._headers()
        except Exception as exc:
            result.fail_step(
                "organisation token",
                f"{s.consumer_org_client_id} could not authenticate: {exc}",
            )
            return None
        status, _ = self.http.raw("GET", f"{s.consumer_connector_url}/health")
        if status != 200:
            result.fail_step(
                "organisation token",
                "the consumer connector does not answer /health",
                url=s.consumer_connector_url,
                status_code=status,
            )
            return None
        return headers

    def _did_service(self, did: str, service_type: str) -> str | None:
        status, document = self.http.raw("GET", _did_web_url(did))
        if status != 200 or not isinstance(document, dict):
            return None
        for entry in document.get("service") or []:
            if isinstance(entry, dict) and entry.get("type") == service_type:
                endpoint = entry.get("serviceEndpoint")
                if isinstance(endpoint, str):
                    return endpoint
        return None

    def _revoke_own(self, headers: dict[str, str], asset_id: str) -> str | None:
        s = self.settings
        status, requests = self.http.raw(
            "GET", f"{s.consumer_connector_url}/consumer/requests", headers=headers
        )
        if status != 200 or not isinstance(requests, list):
            return f"could not list the consumer's requests ({status}): {requests!r}"
        for item in requests:
            if not isinstance(item, dict) or not item.get("can_revoke"):
                continue
            if item.get("asset_id") != asset_id:
                continue
            encoded = urllib.parse.quote(str(item.get("id") or ""), safe="")
            status, body = self.http.raw(
                "POST",
                f"{s.consumer_connector_url}/consumer/requests/{encoded}/revoke",
                body={"reason": REASON},
                headers=headers,
            )
            if status != 200:
                return f"revoke of {item.get('id')} answered {status}: {body!r}"
        return None

    def _exchange(
        self,
        result: FlowResult,
        headers: dict[str, str],
        provider_did: str,
        asset_id: str,
        step: str,
    ) -> Exchange | None:
        """An agreement and a started transfer for `asset_id`, with its EDR.

        Revokes this consumer's earlier requests for the asset first: the
        provider refuses a second live transfer beside one (409), and a request
        left by an interrupted run must not decide this one.
        """
        s = self.settings
        error = self._revoke_own(headers, asset_id)
        if error:
            result.fail_step(step, error)
            return None
        dsp = self._did_service(provider_did, "DSPEndpoint")
        if not dsp:
            result.fail_step(
                step,
                "the provider's DID document names no DSPEndpoint",
                provider=provider_did,
            )
            return None
        status, catalog = self.http.raw(
            "POST",
            f"{s.consumer_connector_url}/consumer/catalog",
            body={
                "counter_party_address": dsp,
                "counter_party_id": provider_did,
                "counter_party_did": provider_did,
            },
            headers=headers,
        )
        if status != 200 or not isinstance(catalog, dict):
            result.fail_step(
                step, "the catalogue request failed", status_code=status, body=catalog
            )
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
                step,
                f"the provider does not offer {asset_id} to this consumer",
                provider=provider_did,
                offered=sorted(
                    str(d.get("@id") or d.get("id"))
                    for d in datasets
                    if isinstance(d, dict)
                ),
            )
            return None
        policy = self._policy(dataset)
        purposes = self._offer_purposes(policy)
        if not purposes:
            result.fail_step(step, f"the offer for {asset_id} permits no purpose")
            return None
        purpose = purposes[0]

        status, negotiated = self.http.raw(
            "POST",
            f"{s.consumer_connector_url}/consumer/negotiate",
            body={
                "counter_party_address": dsp,
                "offer_id": str(policy.get("@id") or f"{asset_id}#offer"),
                "asset_id": asset_id,
                "assigner": provider_did,
                "odrl_policy": policy or None,
                "declared_purpose": [purpose],
                "justification_ref": REASON,
            },
            headers=headers,
        )
        if status != 200 or not isinstance(negotiated, dict):
            result.fail_step(
                step, "the negotiation was refused", status_code=status, body=negotiated
            )
            return None
        negotiation_id = str(negotiated.get("negotiation_id"))
        encoded = urllib.parse.quote(negotiation_id, safe="")
        state = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/negotiations/{encoded}",
            lambda p: (
                p.get("state") == "TERMINATED"
                or (
                    p.get("state") in FINAL_NEGOTIATION_STATES
                    and bool(p.get("contractAgreementId"))
                )
            ),
            headers=headers,
        )
        agreement_id = state.get("contractAgreementId")
        if state.get("state") not in FINAL_NEGOTIATION_STATES or not agreement_id:
            result.fail_step(
                step,
                "the negotiation reached no agreement",
                negotiation_id=negotiation_id,
                state=state.get("state"),
                error=state.get("errorDetail") or state.get("detail"),
            )
            return None

        status, started = self.http.raw(
            "POST",
            f"{s.consumer_connector_url}/consumer/transfer",
            body={
                "contract_agreement_id": agreement_id,
                "counter_party_address": dsp,
                "asset_id": asset_id,
                "connector_id": provider_did,
            },
            headers=headers,
        )
        if status != 200 or not isinstance(started, dict):
            result.fail_step(
                step, "the transfer was refused", status_code=status, body=started
            )
            return None
        transfer_id = str(started.get("transfer_id"))
        encoded = urllib.parse.quote(transfer_id, safe="")
        state = self.http.poll_until(
            f"{s.consumer_connector_url}/consumer/transfers/{encoded}",
            lambda p: p.get("state") in {"STARTED", "TERMINATED"},
            headers=headers,
        )
        if state.get("state") != "STARTED":
            result.fail_step(
                step,
                "the transfer did not start",
                transfer_id=transfer_id,
                state=state.get("state"),
            )
            return None
        # The EDR reaches the connector through EDC's callback, a moment after
        # STARTED; ask until it is there or the poll window is spent.
        edr: Any = None
        deadline = time.monotonic() + s.poll_timeout
        while time.monotonic() < deadline:
            status, edr = self.http.raw(
                "GET",
                f"{s.consumer_connector_url}/consumer/edr/{encoded}",
                headers=headers,
            )
            if status == 200 and isinstance(edr, dict) and edr.get("authorization"):
                break
            time.sleep(s.poll_interval)
        if not (
            isinstance(edr, dict) and edr.get("authorization") and edr.get("endpoint")
        ):
            result.fail_step(
                step,
                "the connector holds no EDR for the transfer",
                transfer_id=transfer_id,
                body=edr,
            )
            return None
        return Exchange(
            asset_id=asset_id,
            agreement_id=str(edr.get("agreement_id") or agreement_id),
            transfer_id=transfer_id,
            token=str(edr["authorization"]),
            endpoint=str(edr["endpoint"]),
            purpose=purpose.rsplit("/", 1)[-1],
            policy=policy,
        )

    def _query(self, exchange: Exchange, sql: str) -> tuple[int, Any]:
        return self.http.post_raw(
            exchange.endpoint,
            {"sql": sql, "limit": QUERY_LIMIT},
            headers={
                "Authorization": exchange.token,
                "Edc-Contract-Agreement-Id": exchange.agreement_id,
                "Edc-Transfer-Process-Id": exchange.transfer_id,
                "Edc-Purpose": exchange.purpose,
            },
        )

    def _organization_counts(
        self, exchange: Exchange, column: str
    ) -> tuple[int, Any, dict[str, int] | None]:
        """Rows per value of the organization column, as the consumer is served."""
        status, body = self._query(
            exchange,
            f"SELECT {column} AS organization, count(*) AS n "
            f"FROM {exchange.asset_id} GROUP BY {column}",
        )
        if status != 200 or not isinstance(body, dict):
            return status, body, None
        counts: dict[str, int] = {}
        for item in body.get("items") or []:
            if isinstance(item, dict):
                counts[str(item.get("organization"))] = int(item.get("n") or 0)
        return status, body, counts

    def _row_count(self, exchange: Exchange) -> tuple[int, Any, int | None]:
        status, body = self._query(
            exchange, f"SELECT count(*) AS n FROM {exchange.asset_id}"
        )
        if status != 200 or not isinstance(body, dict):
            return status, body, None
        items = [i for i in body.get("items") or [] if isinstance(i, dict)]
        return status, body, sum(int(i.get("n") or 0) for i in items)

    def _check_org_rows(
        self, result: FlowResult, exchange: Exchange, step: str
    ) -> bool:
        """Only the consumer's organization's rows, and some of them."""
        s = self.settings
        status, body, counts = self._organization_counts(exchange, s.org_rows_column)
        if counts is None:
            result.fail_step(
                step,
                "the query through the agreement was not answered",
                asset_id=exchange.asset_id,
                status_code=status,
                body=body,
            )
            return False
        others = {k: v for k, v in counts.items() if k != s.consumer_organization_id}
        served = counts.get(s.consumer_organization_id, 0)
        expected = s.org_rows_expected
        if others or served < 1 or (expected is not None and served != expected):
            result.fail_step(
                step,
                "the rows served are not exactly the consumer organization's",
                asset_id=exchange.asset_id,
                organization=s.consumer_organization_id,
                served=counts,
                expected=expected,
            )
            return False
        result.pass_step(
            step,
            f"served {served} row(s), every one of them "
            f"{s.org_rows_column} = {s.consumer_organization_id!r}, and no other "
            "organization's",
            asset_id=exchange.asset_id,
            data_plane=exchange.endpoint,
            served=counts,
        )
        return True

    def _skip_unless(self, result: FlowResult, **settings: Any) -> bool:
        """Skip the flow, naming every setting it lacks; `True` when all are set."""
        missing = [name for name, value in settings.items() if not value]
        if missing:
            result.skip_step(
                "configuration",
                "this deployment names no target for the flow — not asserted in "
                "this run. Missing: " + ", ".join(missing),
            )
            return False
        return True


class OrganizationRowsFlow(_AgreementPathFlow):
    name = "organization-rows"
    description = (
        "Through an agreement, an organization-bound dataset serves only the rows "
        "of the organization the consumer presented; an organization the layer "
        "does not admit gets none"
    )
    rules = ("X-17", "X-18")

    def _assets(self) -> list[str]:
        s = self.settings
        return [s.org_rows_asset_id, s.org_mismatch_asset_id]

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)
        if not self._skip_unless(
            result,
            E2E_CONSUMER_ORGANIZATION_ID=s.consumer_organization_id,
            E2E_ORG_ROWS_PROVIDER_DID=s.org_rows_provider_did,
            E2E_ORG_ROWS_ASSET_ID=s.org_rows_asset_id,
            E2E_ORG_ROWS_COLUMN=s.org_rows_column,
        ):
            return result
        headers = self._authenticate(result)
        if headers is None:
            return result

        exchange = self._exchange(
            result, headers, s.org_rows_provider_did, s.org_rows_asset_id, "agreement"
        )
        if exchange is not None:
            result.pass_step(
                "agreement",
                "the consumer organisation holds a live transfer for the "
                "organization-bound dataset",
                asset_id=exchange.asset_id,
                agreement_id=exchange.agreement_id,
            )
            self._check_org_rows(result, exchange, "only its own organization's rows")

        if not (s.org_mismatch_provider_did and s.org_mismatch_asset_id):
            result.skip_step(
                "an organization the layer does not admit gets no rows",
                "E2E_ORG_MISMATCH_PROVIDER_DID / E2E_ORG_MISMATCH_ASSET_ID unset — "
                "not asserted in this run",
            )
        else:
            mismatch = self._exchange(
                result,
                headers,
                s.org_mismatch_provider_did,
                s.org_mismatch_asset_id,
                "an organization the layer does not admit gets no rows",
            )
            if mismatch is not None:
                status, body, rows = self._row_count(mismatch)
                if status != 200 or rows != 0:
                    result.fail_step(
                        "an organization the layer does not admit gets no rows",
                        "the dataset served rows to a consumer whose organization "
                        "its organization layer does not admit, or did not answer",
                        asset_id=mismatch.asset_id,
                        status_code=status,
                        rows=rows,
                        body=body if rows is None else None,
                    )
                else:
                    result.pass_step(
                        "an organization the layer does not admit gets no rows",
                        "a live agreement, an answered query, and zero rows: the "
                        "agreement did not lift the organization layer",
                        asset_id=mismatch.asset_id,
                        data_plane=mismatch.endpoint,
                    )

        for asset_id in self._assets():
            if asset_id:
                self._revoke_own(headers, asset_id)
        return result


class LayerVerdictsFlow(_AgreementPathFlow):
    name = "layer-verdicts"
    description = (
        "`allow_all` is no consent signal and `deny_all` refuses the query, "
        "through a live agreement"
    )
    rules = ("X-19",)

    def _assets(self) -> list[str]:
        s = self.settings
        return [s.org_rows_asset_id, s.deny_all_asset_id]

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)
        if not self._skip_unless(
            result,
            E2E_DENY_ALL_PROVIDER_DID=s.deny_all_provider_did,
            E2E_DENY_ALL_ASSET_ID=s.deny_all_asset_id,
            E2E_ORG_ROWS_PROVIDER_DID=s.org_rows_provider_did,
            E2E_ORG_ROWS_ASSET_ID=s.org_rows_asset_id,
        ):
            return result
        headers = self._authenticate(result)
        if headers is None:
            return result

        # `allow_all` on the person layer: no consent constraint offered, no
        # consent asked for, and the query is answered — never `no_consent` or
        # `purpose_required`, which is what a consent-gated dataset answers a
        # consumer that names nobody.
        step = "allow_all is no consent signal"
        allowed = self._exchange(
            result, headers, s.org_rows_provider_did, s.org_rows_asset_id, step
        )
        if allowed is not None:
            if self._policy_requires_consent(allowed.policy):
                result.fail_step(
                    step,
                    "the offer carries a consent constraint",
                    asset_id=allowed.asset_id,
                )
            else:
                status, body = self._query(
                    allowed, f"SELECT count(*) AS n FROM {allowed.asset_id}"
                )
                if status != 200:
                    result.fail_step(
                        step,
                        "a query naming no person was refused",
                        asset_id=allowed.asset_id,
                        status_code=status,
                        body=body,
                    )
                else:
                    result.pass_step(
                        step,
                        "offered with no consent constraint, agreed with no consent "
                        "on record, and queried with no person named: answered",
                        asset_id=allowed.asset_id,
                        data_plane=allowed.endpoint,
                    )

        step = "deny_all refuses the query"
        denied = self._exchange(
            result, headers, s.deny_all_provider_did, s.deny_all_asset_id, step
        )
        if denied is not None:
            status, body = self._query(
                denied, f"SELECT count(*) AS n FROM {denied.asset_id}"
            )
            if status != 403 or "row_policy_denied" not in json.dumps(body):
                result.fail_step(
                    step,
                    "a dataset declaring deny_all was not refused with "
                    "row_policy_denied",
                    asset_id=denied.asset_id,
                    status_code=status,
                    body=body,
                )
            else:
                result.pass_step(
                    step,
                    "a live agreement, and the query refused: row_policy_denied",
                    asset_id=denied.asset_id,
                    data_plane=denied.endpoint,
                    body=body,
                )

        for asset_id in self._assets():
            if asset_id:
                self._revoke_own(headers, asset_id)
        return result


class OrganizationReissueFlow(_AgreementPathFlow):
    name = "organization-reissue"
    description = (
        "`ir-cli org reissue` delivers a successor and suspends the predecessor; "
        "the holder presents only the successor and the exchange still works"
    )
    rules = ("P-30", "P-31")

    def _assets(self) -> list[str]:
        return [self.settings.org_rows_asset_id]

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)
        if not self._skip_unless(
            result,
            E2E_IR_CLI_COMMAND=s.ir_cli_command,
            E2E_CONSUMER_ORGANIZATION_ALIAS=s.consumer_organization_alias,
            E2E_CONSUMER_ORGANIZATION_ID=s.consumer_organization_id,
            E2E_ORG_ROWS_PROVIDER_DID=s.org_rows_provider_did,
            E2E_ORG_ROWS_ASSET_ID=s.org_rows_asset_id,
            E2E_ORG_ROWS_COLUMN=s.org_rows_column,
        ):
            return result

        before = self._presented(result, "presented before the reissue")
        if before is None:
            return result
        held = [c for c in before if c.organization_id == s.consumer_organization_id]
        if not held:
            result.fail_step(
                "presented before the reissue",
                "the holder presents no OrganizationCredential naming its organization",
                presented=[c.id for c in before],
            )
            return result
        result.pass_step(
            "presented before the reissue",
            "the holder presents its current OrganizationCredential",
            presented=[c.id for c in held],
        )

        reissue = self._reissue(result)
        if reissue is None:
            return result
        successor = str(reissue["issued"])
        suspended = set(reissue["suspended"])
        missing = sorted({c.id for c in held} - suspended)
        if missing:
            result.fail_step(
                "successor delivered, predecessor suspended",
                "the reissue left a presented predecessor unsuspended",
                not_suspended=missing,
                output=reissue,
            )
            return result
        result.pass_step(
            "successor delivered, predecessor suspended",
            "issued and delivered to the holder's store, then the predecessor "
            "suspended",
            successor=successor,
            suspended=sorted(suspended),
        )

        self._check_register(result, held)

        after = self._presented(result, "the holder presents the successor only")
        if after is not None:
            ids = {c.id for c in after}
            retired = sorted(ids & suspended)
            current = next((c for c in after if c.id == successor), None)
            if retired or current is None:
                result.fail_step(
                    "the holder presents the successor only",
                    "the holder presented a suspended credential, or not its successor",
                    presented=sorted(ids),
                    successor=successor,
                    suspended_presented=retired or None,
                )
            elif current.organization_id != s.consumer_organization_id:
                result.fail_step(
                    "the holder presents the successor only",
                    "the successor names another organization",
                    organization_id=current.organization_id,
                )
            else:
                result.pass_step(
                    "the holder presents the successor only",
                    "the suspended predecessor is left out of the presentation; the "
                    "successor carries the same organization",
                    presented=sorted(ids),
                )

        headers = self._authenticate(result)
        if headers is None:
            return result
        exchange = self._exchange(
            result,
            headers,
            s.org_rows_provider_did,
            s.org_rows_asset_id,
            "an exchange after the reissue",
        )
        if exchange is not None:
            result.pass_step(
                "an exchange after the reissue",
                "negotiated and started on the successor alone",
                agreement_id=exchange.agreement_id,
            )
            self._check_org_rows(
                result, exchange, "the organization is still established"
            )
        self._revoke_own(headers, s.org_rows_asset_id)
        return result

    # ── the holder, as a verifier sees it ──────────────────────────────────

    def _sts_token(self, did: str, secret: str, **form: str) -> str | None:
        status, payload = self.http.raw(
            "POST",
            f"{_participant_base(did)}/sts/{urllib.parse.quote(did, safe='')}/token",
            form={
                "grant_type": "client_credentials",
                "client_id": did,
                "client_secret": secret,
                **form,
            },
        )
        if status != 200 or not isinstance(payload, dict):
            return None
        token = payload.get("access_token")
        return str(token) if token else None

    def _presented(
        self, result: FlowResult, step: str
    ) -> list[PresentedCredential] | None:
        """The consumer's OrganizationCredentials, as its holder presents them.

        The DCP exchange a counterparty's EDC runs, done by hand: the holder's
        STS grants the verifier `OrganizationCredential:read`, the verifier's STS
        wraps the grant in its own self-issued token, and the holder's credential
        service answers that. What comes back is what a verifier sees.
        """
        s = self.settings
        holder, verifier = s.consumer_did, s.provider_did
        holder_token = self._sts_token(
            holder,
            s.consumer_sts_client_secret,
            bearer_access_scope=ORGANIZATION_SCOPE,
            audience=verifier,
        )
        grant = _jwt_claims(holder_token).get("token") if holder_token else None
        if not grant:
            result.fail_step(
                step, "the holder's STS granted no presentation scope", holder=holder
            )
            return None
        verifier_token = self._sts_token(
            verifier, s.provider_sts_client_secret, token=str(grant), audience=holder
        )
        if not verifier_token:
            result.fail_step(
                step, "the verifier's STS issued no token", verifier=verifier
            )
            return None
        service = self._did_service(holder, "CredentialService")
        if not service:
            result.fail_step(
                step, "the holder's DID document names no CredentialService"
            )
            return None
        status, body = self.http.raw(
            "POST",
            f"{service.rstrip('/')}/presentations/query",
            body={
                "@context": ["https://w3id.org/tractusx-trust/v0.8"],
                "@type": "PresentationQueryMessage",
                "scope": [ORGANIZATION_SCOPE],
            },
            headers={"Authorization": f"Bearer {verifier_token}"},
        )
        if status != 200:
            result.fail_step(
                step,
                "the holder's credential service did not answer the verifier",
                status_code=status,
                body=body,
            )
            return None
        return [
            c
            for c in presented_credentials(body)
            if "OrganizationCredential" in c.types
        ]

    # ── the anchor ─────────────────────────────────────────────────────────

    def _reissue(self, result: FlowResult) -> dict[str, Any] | None:
        s = self.settings
        argv = [
            *shlex.split(s.ir_cli_command),
            "org",
            "reissue",
            "--alias",
            s.consumer_organization_alias,
        ]
        step = "successor delivered, predecessor suspended"
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as exc:
            result.fail_step(step, f"`ir-cli org reissue` could not run: {exc}")
            return None
        parsed = parse_reissue(proc.stdout)
        if proc.returncode != 0 or not parsed["issued"] or not parsed["delivered"]:
            result.fail_step(
                step,
                "`ir-cli org reissue` did not issue and deliver a successor",
                returncode=proc.returncode,
                stdout=proc.stdout[-2000:],
                stderr=proc.stderr[-2000:],
            )
            return None
        return parsed

    def _check_register(
        self, result: FlowResult, predecessors: list[PresentedCredential]
    ) -> None:
        """Suspended, not revoked — on the register every verifier reads."""
        step = "suspended on the issuer's register, not revoked"
        lists: dict[str, str] = {}
        seen: dict[str, dict[str, bool]] = {}
        for credential in predecessors:
            bits: dict[str, bool] = {}
            for purpose in ("suspension", "revocation"):
                entry = credential.status.get(purpose)
                if entry is None:
                    continue
                url, index = entry
                if url not in lists:
                    status, body = self.http.raw("GET", url, headers={"Accept": "*/*"})
                    if status != 200 or not isinstance(body, str):
                        result.fail_step(
                            step,
                            "the status list is not readable",
                            url=url,
                            status_code=status,
                        )
                        return
                    vc = _jwt_claims(body.strip())
                    subject = (vc.get("vc") or vc).get("credentialSubject") or {}
                    if isinstance(subject, list):
                        subject = subject[0] if subject else {}
                    lists[url] = str(subject.get("encodedList") or "")
                try:
                    bits[purpose] = status_bit(lists[url], index)
                except (ValueError, OSError, IndexError) as exc:
                    result.fail_step(step, f"the status list is unreadable: {exc}")
                    return
            seen[credential.id] = bits
        wrong = {
            cid: bits
            for cid, bits in seen.items()
            if bits.get("suspension") is not True or bits.get("revocation") is True
        }
        if wrong:
            result.fail_step(
                step,
                "a predecessor is not suspended, or is revoked",
                bits=wrong,
            )
            return
        result.pass_step(
            step,
            "the suspension bit is set and the revocation bit is not",
            bits=seen,
        )
