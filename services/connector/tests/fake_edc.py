"""A stateful stand-in for one participant context's EDC Management API.

**Why it holds state rather than recording calls.** The previous stub answered
every call with `...` and remembered only the assets that were created. Against
that, a sync that *withdraws* nothing and a sync that withdraws correctly are
indistinguishable — there is no "what EDC holds" for the reconcile to read, so
the test for the stale-asset defect could not fail. That is the exact shape of
defect the plan `a-participant-publishes-and-the-sync-reconciles` exists for, so
the stub is the first thing it fixes.

It models only what `sync_governance` uses, and it models EDC's two refusals that
matter to the reconcile, because both decide the order the sync has to delete in:

* a **contract definition** referencing a policy makes that policy undeletable
  (EDC answers 409);
* an **asset** may be pinned by an agreement, which the fake exposes as
  ``pin_asset`` and answers 409 for.

A 404 on a delete is *not* an error here, matching `ds_edc.client`: absence is
the goal of a delete.
"""

from __future__ import annotations

from typing import Any

import httpx


def _conflict(operation: str, detail: str) -> httpx.HTTPStatusError:
    request = httpx.Request("DELETE", f"https://edc.test/{operation}")
    response = httpx.Response(409, request=request, text=detail)
    return httpx.HTTPStatusError(
        f"EDC {operation} 409: {detail}", request=request, response=response
    )


class FakeEdc:
    """What one EDC holds, and what the sync did to it."""

    def __init__(self) -> None:
        #: asset id → the asset document, as `list_assets` would return it.
        self.assets: dict[str, dict[str, Any]] = {}
        self.policies: dict[str, dict[str, Any]] = {}
        self.contract_definitions: dict[str, dict[str, Any]] = {}
        #: Assets EDC refuses to delete (they have agreements).
        self.pinned_assets: set[str] = set()
        #: Every call, in order — so a test can assert the *order* of deletes,
        #: which is the half of the reconcile EDC's own rules decide.
        self.calls: list[tuple[str, str]] = []

    # -- seeding ------------------------------------------------------------

    def seed_published(
        self,
        asset_id: str,
        dataset_key: str,
        *,
        prefix: str = "ds",
        policy_ids: tuple[str, ...] = (),
        contract_id: str | None = None,
    ) -> None:
        """Put a previously-published dataset in EDC, the way a real sync leaves it."""
        self.assets[asset_id] = {
            "@id": asset_id,
            "properties": {f"{prefix}:datasetKey": dataset_key},
        }
        for policy_id in policy_ids:
            self.policies[policy_id] = {"@id": policy_id}
        if contract_id:
            self.contract_definitions[contract_id] = {
                "@id": contract_id,
                "accessPolicyId": policy_ids[0] if policy_ids else "",
                "contractPolicyId": policy_ids[-1] if policy_ids else "",
                "assetsSelector": [
                    {
                        "operandLeft": "id",
                        "operator": "=",
                        "operandRight": asset_id,
                    }
                ],
            }

    def seed_foreign_asset(self, asset_id: str) -> None:
        """An asset ds did not publish: no `datasetKey`, and not ds's to remove."""
        self.assets[asset_id] = {"@id": asset_id, "properties": {"name": "not ours"}}

    # -- the API ------------------------------------------------------------

    async def list_assets(self) -> list[dict[str, Any]]:
        self.calls.append(("list_assets", ""))
        return list(self.assets.values())

    async def list_contract_definitions(self) -> list[dict[str, Any]]:
        self.calls.append(("list_contract_definitions", ""))
        return list(self.contract_definitions.values())

    async def create_asset(self, payload) -> dict[str, Any]:
        self.calls.append(("create_asset", payload.id))
        self.assets[payload.id] = {
            "@id": payload.id,
            "properties": dict(payload.properties),
        }
        return self.assets[payload.id]

    async def delete_asset(self, asset_id: str) -> None:
        self.calls.append(("delete_asset", asset_id))
        if asset_id in self.pinned_assets:
            raise _conflict("delete_asset", "asset has contract agreements")
        self.assets.pop(asset_id, None)

    async def update_asset(self, payload) -> None:
        self.calls.append(("update_asset", payload.id))
        self.assets[payload.id] = {
            "@id": payload.id,
            "properties": dict(payload.properties),
        }

    async def create_policy(self, payload) -> dict[str, Any]:
        self.calls.append(("create_policy", payload.id))
        self.policies[payload.id] = {"@id": payload.id}
        return self.policies[payload.id]

    async def delete_policy(self, policy_id: str) -> None:
        self.calls.append(("delete_policy", policy_id))
        referencing = [
            cd_id
            for cd_id, cd in self.contract_definitions.items()
            if policy_id in (cd.get("accessPolicyId"), cd.get("contractPolicyId"))
        ]
        if referencing:
            raise _conflict(
                "delete_policy",
                f"policy is referenced by contract definition {referencing[0]}",
            )
        self.policies.pop(policy_id, None)

    async def create_contract_definition(self, payload) -> dict[str, Any]:
        self.calls.append(("create_contract_definition", payload.id))
        self.contract_definitions[payload.id] = {
            "@id": payload.id,
            "accessPolicyId": getattr(payload, "access_policy_id", ""),
            "contractPolicyId": getattr(payload, "contract_policy_id", ""),
            "assetsSelector": list(getattr(payload, "assets_selector", []) or []),
        }
        return self.contract_definitions[payload.id]

    async def delete_contract_definition(self, contract_id: str) -> None:
        self.calls.append(("delete_contract_definition", contract_id))
        self.contract_definitions.pop(contract_id, None)

    # -- assertions helpers -------------------------------------------------

    @property
    def created_assets(self) -> list[str]:
        """Asset ids this sync created, in order — the old stub's whole surface."""
        return [target for name, target in self.calls if name == "create_asset"]


class NullProv:
    """A `ProvBridge` that records nothing — for tests about EDC, not the graph.

    ``events`` is here so a test that *is* about the graph can read it without a
    second double: a null object that silently swallows an emitter it does not
    declare would let a missing call site pass as success, which is the failure
    `test_prov_bridge_emitters.py` exists to prevent.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def catalogue_published(self, **kwargs):
        self.events.append(("CataloguePublished", kwargs))

    async def catalogue_withdrawn(self, **kwargs):
        self.events.append(("CatalogueWithdrawn", kwargs))

    def emitted(self, event_type: str) -> list[dict]:
        return [payload for name, payload in self.events if name == event_type]
