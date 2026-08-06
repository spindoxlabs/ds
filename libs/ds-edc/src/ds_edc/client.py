"""Async httpx client for EDC Management API v3."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx

from .schemas import (
    AssetCreate,
    CatalogRequest,
    ContractDefCreate,
    EdrResponse,
    NegotiationRequest,
    NegotiationState,
    PolicyCreate,
    TransferRequest,
    TransferState,
)

log = logging.getLogger(__name__)

_FINALIZED_STATES = {"FINALIZED", "VERIFIED", "AGREED"}
# EDC's ContractNegotiationStates and TransferProcessStates enums have no
# `ERROR` member — a failure is carried as `errorDetail` on a `TERMINATED`
# entity. The name used to sit in both sets, so it read as a handled case and
# could never match. Removing it is not a behaviour change; keeping it was a
# claim that this client handles a state EDC does not produce.
_TERMINAL_STATES = {"TERMINATED"}
_ACTIVE_TRANSFER_STATES = {"STARTED"}
_TERMINAL_TRANSFER_STATES = {"COMPLETED", "TERMINATED", "DEPROVISIONING_REQUESTED"}

EDC_CONTEXT = {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"}

_QUERY_SPEC = {"@context": EDC_CONTEXT, "@type": "QuerySpec"}


class EdcPollTimeout(TimeoutError):
    """A poll gave up before the entity reached a state worth reporting.

    Rulebook, data exchange X-10: *a timeout is reported as a timeout, never as
    a terminal protocol state.* Both polls used to synthesise
    ``state="TIMEOUT"`` and hand it back in a ``NegotiationState`` /
    ``TransferState``, where callers compared it against real EDC state names —
    so "we stopped waiting" was indistinguishable from "the counterparty
    refused", and the value would have collided outright with a real state had
    EDC ever added one by that name.
    """

    def __init__(self, entity: str, entity_id: str, timeout: float, last_state: str):
        self.entity = entity
        self.entity_id = entity_id
        self.timeout = timeout
        #: The last state actually observed, for the operator who has to work
        #: out whether this was a stall or a slow counterparty.
        self.last_state = last_state
        super().__init__(
            f"{entity} {entity_id} did not reach a terminal state within {timeout}s "
            f"(last observed state: {last_state or 'none'})"
        )


def _path_id(value: str) -> str:
    return quote(value, safe="")


class EdcManagementClient:
    """Typed async wrapper around the EDC Management API v3."""

    def __init__(self, base_url: str, api_key: str | None = None):
        headers: dict[str, str] = {}
        if api_key:
            headers["X-Api-Key"] = api_key
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _raise_with_body(r: httpx.Response, operation: str) -> None:
        """Turn a failed response into an error that names what EDC said.

        Used on **every** request. It was previously on six of thirty methods,
        and the rest raised through ``httpx.raise_for_status()``, whose message
        carries the status line and not the body — so an EDC that explains a 400
        in its response ("policy definition not found", "asset already exists")
        reached the operator as a bare *Client error '400 Bad Request'*.
        """
        if r.is_success:
            return
        body = r.text[:500]
        log.error("EDC %s failed (%s): %s", operation, r.status_code, body)
        raise httpx.HTTPStatusError(
            f"EDC {operation} {r.status_code}: {body}",
            request=r.request,
            response=r,
        )

    @staticmethod
    def _created_id(r: httpx.Response, operation: str) -> str:
        """The ``@id`` EDC assigns to something it just created.

        Read straight off ``r.json()["@id"]`` before, which raises ``KeyError``
        or ``TypeError`` — neither of which names the operation or the payload —
        on any 2xx that is not the shape expected.
        """
        try:
            data = r.json()
        except ValueError as exc:
            raise ValueError(
                f"EDC {operation} returned {r.status_code} with a non-JSON body: "
                f"{r.text[:200]!r}"
            ) from exc
        if not isinstance(data, dict) or not data.get("@id"):
            raise ValueError(
                f"EDC {operation} returned {r.status_code} without an '@id': {data!r}"
            )
        return str(data["@id"])

    # -- Assets ---------------------------------------------------------------

    async def create_asset(self, asset: AssetCreate) -> dict[str, Any]:
        r = await self._http.post("/v3/assets", json=asset.to_edc())
        self._raise_with_body(r, "create_asset")
        data: dict[str, Any] = r.json()
        return data

    async def get_asset(self, asset_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/v3/assets/{_path_id(asset_id)}")
        self._raise_with_body(r, "get_asset")
        data: dict[str, Any] = r.json()
        return data

    async def list_assets(self) -> list[dict[str, Any]]:
        r = await self._http.post("/v3/assets/request", json=_QUERY_SPEC)
        self._raise_with_body(r, "list_assets")
        data: list[dict[str, Any]] = r.json()
        return data

    async def delete_asset(self, asset_id: str) -> None:
        # A 404 on a *delete* is the requested end state reached by another
        # route: the asset is not there. That is not the same argument as the
        # one the terminate calls used to make — see `terminate_negotiation`.
        r = await self._http.delete(f"/v3/assets/{_path_id(asset_id)}")
        if r.status_code != 404:
            self._raise_with_body(r, "delete_asset")

    # -- Policies -------------------------------------------------------------

    async def create_policy(self, policy: PolicyCreate) -> dict[str, Any]:
        r = await self._http.post("/v3/policydefinitions", json=policy.to_edc())
        self._raise_with_body(r, "create_policy")
        data: dict[str, Any] = r.json()
        return data

    async def list_policies(self) -> list[dict[str, Any]]:
        # `{}` has no `@context`, so EDC expands it against no vocabulary and
        # the QuerySpec's own defaults apply by accident rather than by request.
        # Every other list call on this client sends the JSON-LD form.
        r = await self._http.post("/v3/policydefinitions/request", json=_QUERY_SPEC)
        self._raise_with_body(r, "list_policies")
        data: list[dict[str, Any]] = r.json()
        return data

    async def delete_policy(self, policy_id: str) -> None:
        r = await self._http.delete(f"/v3/policydefinitions/{_path_id(policy_id)}")
        if r.status_code != 404:
            self._raise_with_body(r, "delete_policy")

    # -- Contract Definitions -------------------------------------------------

    async def create_contract_definition(self, cd: ContractDefCreate) -> dict[str, Any]:
        r = await self._http.post("/v3/contractdefinitions", json=cd.to_edc())
        self._raise_with_body(r, "create_contract_definition")
        data: dict[str, Any] = r.json()
        return data

    async def list_contract_definitions(self) -> list[dict[str, Any]]:
        r = await self._http.post("/v3/contractdefinitions/request", json=_QUERY_SPEC)
        self._raise_with_body(r, "list_contract_definitions")
        data: list[dict[str, Any]] = r.json()
        return data

    async def delete_contract_definition(self, cid: str) -> None:
        r = await self._http.delete(f"/v3/contractdefinitions/{_path_id(cid)}")
        if r.status_code != 404:
            self._raise_with_body(r, "delete_contract_definition")

    # -- Catalog --------------------------------------------------------------

    async def request_catalog(self, req: CatalogRequest) -> dict[str, Any]:
        r = await self._http.post("/v3/catalog/request", json=req.to_edc())
        self._raise_with_body(r, "request_catalog")
        data: dict[str, Any] = r.json()
        return data

    # -- Negotiation ----------------------------------------------------------

    async def start_negotiation(self, req: NegotiationRequest) -> str:
        r = await self._http.post("/v3/contractnegotiations", json=req.to_edc())
        self._raise_with_body(r, "start_negotiation")
        return self._created_id(r, "start_negotiation")

    async def get_negotiation(self, negotiation_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/v3/contractnegotiations/{_path_id(negotiation_id)}")
        self._raise_with_body(r, "get_negotiation")
        data: dict[str, Any] = r.json()
        return data

    async def poll_negotiation(
        self,
        negotiation_id: str,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
    ) -> NegotiationState:
        # `elapsed` used to advance by `poll_interval` alone, ignoring how long
        # each `get_negotiation` took. Against a slow or hanging control plane —
        # exactly when a timeout matters — the loop ran for far longer than the
        # caller asked for. A monotonic deadline measures the wait that actually
        # happened, and does not move when the system clock does.
        deadline = time.monotonic() + timeout
        state = ""
        while True:
            data = await self.get_negotiation(negotiation_id)
            state = data.get("state", "")
            agreement_id = data.get("contractAgreementId")
            if state in _FINALIZED_STATES:
                return NegotiationState(
                    negotiation_id=negotiation_id,
                    state=state,
                    contract_agreement_id=agreement_id,
                )
            if state in _TERMINAL_STATES:
                return NegotiationState(
                    negotiation_id=negotiation_id,
                    state=state,
                    error_detail=data.get("errorDetail"),
                )
            if time.monotonic() + poll_interval >= deadline:
                raise EdcPollTimeout("Negotiation", negotiation_id, timeout, state)
            await asyncio.sleep(poll_interval)

    async def terminate_negotiation(self, negotiation_id: str, reason: str) -> None:
        """Terminate a negotiation — the refusal and TTL-expiry path.

        Unlike resuming, this is plain Management API: a subject's refusal and a
        parked negotiation's TTL both end in the same place a counterparty
        walking away would, so no custom endpoint is needed.

        **A failed termination raises** (rulebook, data exchange X-11). ``404``
        and ``409`` were both swallowed, and the connector then answered
        ``{"terminated": true}``. The 409 case is the one that matters: EDC
        returns it for a negotiation whose state forbids termination, and
        ``FINALIZED`` is such a state — so a refusal arriving just after the
        agreement was signed reported success while the agreement, and the
        consumer's access, stood.

        409 is not simply re-raised, because a negotiation already ``TERMINATED``
        also answers 409 and the TTL sweep retries into it. That case is settled
        by **reading the state back**: already terminated is a success this
        client observed, rather than one it assumed.
        """
        r = await self._http.post(
            f"/v3/contractnegotiations/{_path_id(negotiation_id)}/terminate",
            json={
                "@context": EDC_CONTEXT,
                "@type": "TerminateNegotiation",
                "@id": negotiation_id,
                "reason": reason,
            },
        )
        if r.status_code == 409 and await self._already_terminated(
            "negotiation", negotiation_id
        ):
            return
        self._raise_with_body(r, "terminate negotiation")

    async def _already_terminated(self, kind: str, entity_id: str) -> bool:
        """Whether a 409'd terminate target is already in ``TERMINATED``."""
        getter = self.get_negotiation if kind == "negotiation" else self.get_transfer
        try:
            state = (await getter(entity_id)).get("state", "")
        except (httpx.HTTPError, ValueError) as exc:
            log.warning(
                "Could not read %s %s back after a 409 on terminate: %s",
                kind, entity_id, exc,
            )
            return False
        if state == "TERMINATED":
            log.info("%s %s was already TERMINATED", kind.capitalize(), entity_id)
            return True
        log.error(
            "%s %s refused termination and is in state %s, not TERMINATED",
            kind.capitalize(), entity_id, state,
        )
        return False

    async def resume_negotiation(self, negotiation_id: str) -> dict[str, Any]:
        """Clear ``pending`` on a negotiation parked by the consent guard.

        Served by ``NegotiationResumeController`` in our EDC extension, because
        the Management API has no way to clear ``pending`` at EDC 0.16.0. Local
        to the provider's own control plane — never a DSP message.

        Idempotent, and deliberately not an error when nothing happens: a grant
        arriving after the TTL terminated the negotiation returns
        ``outcome="terminal"`` so the caller can record the race rather than
        retry into it forever.
        """
        r = await self._http.post(
            f"/dataspaces/negotiations/{_path_id(negotiation_id)}/resume"
        )
        if r.status_code == 404:
            return {"id": negotiation_id, "resumed": False, "outcome": "not_found"}
        self._raise_with_body(r, "resume negotiation")
        data: dict[str, Any] = r.json()
        return data

    # -- Transfer -------------------------------------------------------------

    async def start_transfer(self, req: TransferRequest) -> str:
        r = await self._http.post("/v3/transferprocesses", json=req.to_edc())
        self._raise_with_body(r, "start_transfer")
        return self._created_id(r, "start_transfer")

    async def get_transfer(self, transfer_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/v3/transferprocesses/{_path_id(transfer_id)}")
        self._raise_with_body(r, "get_transfer")
        data: dict[str, Any] = r.json()
        return data

    async def terminate_transfer(
        self, transfer_id: str, reason: str | None = None
    ) -> None:
        """Terminate a running transfer — the consent-revocation path.

        **A failed termination raises** (rulebook, data exchange X-11). ``404``
        and ``405`` were logged and swallowed, under the heading *"termination
        endpoint unavailable"* — but a 405 means this EDC does not serve the
        route at all, and the caller was told the transfer had stopped. That is
        the revocation path: a data subject withdrew consent, the transfer kept
        running, and the portal showed it as revoked.

        As on the negotiation side, a 409 is checked against the transfer's own
        state so that re-revoking an already-terminated transfer stays
        idempotent without assuming anything.
        """
        r = await self._http.post(
            f"/v3/transferprocesses/{_path_id(transfer_id)}/terminate",
            json={
                "@context": EDC_CONTEXT,
                "@type": "TerminateTransfer",
                "reason": reason or "Revoked by consumer",
            },
        )
        if r.status_code == 409 and await self._already_terminated(
            "transfer", transfer_id
        ):
            return
        self._raise_with_body(r, "terminate transfer")

    async def poll_transfer(
        self,
        transfer_id: str,
        poll_interval: float = 2.0,
        timeout: float = 120.0,
    ) -> TransferState:
        deadline = time.monotonic() + timeout
        state = ""
        while True:
            data = await self.get_transfer(transfer_id)
            state = data.get("state", "")
            if state in _ACTIVE_TRANSFER_STATES:
                return TransferState(transfer_id=transfer_id, state=state)
            if state in _TERMINAL_TRANSFER_STATES:
                return TransferState(
                    transfer_id=transfer_id,
                    state=state,
                    error_detail=data.get("errorDetail"),
                )
            if time.monotonic() + poll_interval >= deadline:
                raise EdcPollTimeout("Transfer", transfer_id, timeout, state)
            await asyncio.sleep(poll_interval)

    async def list_transfers(self) -> list[dict[str, Any]]:
        r = await self._http.post("/v3/transferprocesses/request", json=_QUERY_SPEC)
        self._raise_with_body(r, "list_transfers")
        data: list[dict[str, Any]] = r.json()
        return data

    # -- EDR ------------------------------------------------------------------

    async def get_edr(self, transfer_id: str) -> EdrResponse:
        r = await self._http.get(f"/v3/edrs/{_path_id(transfer_id)}/dataaddress")
        self._raise_with_body(r, "get_edr")
        return EdrResponse.from_edc(r.json())

    # -- Query helpers (used by history API) ----------------------------------

    async def query_negotiations(
        self, offset: int = 0, limit: int = 50, state: str | None = None,
    ) -> list[dict[str, Any]]:
        query_spec: dict[str, Any] = {
            "@context": EDC_CONTEXT,
            "@type": "QuerySpec",
            "offset": offset,
            "limit": limit,
            "sortOrder": "DESC",
            "sortField": "createdAt",
        }
        if state:
            query_spec["filterExpression"] = [{
                "operandLeft": "state",
                "operator": "=",
                "operandRight": state,
            }]
        r = await self._http.post(
            "/v3/contractnegotiations/request", json=query_spec
        )
        self._raise_with_body(r, "query_negotiations")
        data: list[dict[str, Any]] = r.json()
        return data

    async def query_transfers(
        self, offset: int = 0, limit: int = 50, state: str | None = None,
    ) -> list[dict[str, Any]]:
        query_spec: dict[str, Any] = {
            "@context": EDC_CONTEXT,
            "@type": "QuerySpec",
            "offset": offset,
            "limit": limit,
            "sortOrder": "DESC",
            "sortField": "createdAt",
        }
        if state:
            query_spec["filterExpression"] = [{
                "operandLeft": "state",
                "operator": "=",
                "operandRight": state,
            }]
        r = await self._http.post("/v3/transferprocesses/request", json=query_spec)
        self._raise_with_body(r, "query_transfers")
        data: list[dict[str, Any]] = r.json()
        return data

    async def get_agreement(self, agreement_id: str) -> dict[str, Any]:
        r = await self._http.get(f"/v3/contractagreements/{_path_id(agreement_id)}")
        self._raise_with_body(r, "get_agreement")
        data: dict[str, Any] = r.json()
        return data
