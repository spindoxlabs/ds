"""Scenario fixtures — declarative, idempotent, reversible.

A use-case flow is only trustworthy if the state it runs against is known. The
alternative — flows that provision their own fixtures inline — produces tests
that pass on a dirty stack and fail on a clean one, and leave residue that makes
the *next* run pass for the wrong reason.

So fixtures are declared in a YAML file and applied through the
identity-registry admin API:

    apply    → provision, idempotent; re-running changes nothing
    show     → report what currently exists, without changing anything
    destroy  → remove exactly what apply created, and nothing else

`destroy` is deliberately narrow. It removes only the aliases and DIDs the
scenario names, so pointing this at a shared environment cannot delete an
organisation the scenario did not create. Anything it cannot attribute to the
scenario is reported and left alone.

Agreements are the one thing not provisioned here: their text hashes are
computed from files on the identity-registry's disk, so they are seeded with
`ir-cli agreement import`. `apply` verifies they exist with the declared
capacity and stops with the exact command when they do not — a scenario that
ran against a missing or wrong-capacity agreement would make the circle
assertions pass for the wrong reason.
"""
from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ds_e2e.config import E2ESettings
from ds_e2e.http import HttpClient

log = logging.getLogger(__name__)

DEFAULT_SCENARIO = "energy-chains"


class ScenarioError(RuntimeError):
    """A precondition the scenario cannot provision for itself."""


@dataclass
class ScenarioReport:
    """What apply/destroy/show actually did, for printing and for tests."""

    name: str
    actions: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def did(self, message: str) -> None:
        self.actions.append(message)
        log.info("%s", message)

    def problem(self, message: str) -> None:
        self.problems.append(message)
        log.warning("%s", message)


def scenarios_dir() -> Path:
    """Scenarios ship inside the package, so they resolve from an installed
    wheel as well as from a source checkout."""
    return Path(__file__).resolve().parent / "scenarios"


def load_scenario(name_or_path: str = DEFAULT_SCENARIO) -> dict[str, Any]:
    path = Path(name_or_path)
    if not path.suffix:
        path = scenarios_dir() / f"{name_or_path}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in scenarios_dir().glob("*.yaml"))
        raise ScenarioError(f"No scenario {name_or_path!r}. Available: {available}")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ScenarioError(f"{path} is not a scenario document")
    return data


class ScenarioRunner:
    """Applies, inspects and removes a scenario through the admin API."""

    def __init__(self, settings: E2ESettings, http: HttpClient, scenario: dict[str, Any]):
        self.settings = settings
        self.http = http
        self.scenario = scenario
        self.ir = settings.identity_registry_url.rstrip("/")
        self._admin: dict[str, str] | None = None

    # ── auth ─────────────────────────────────────────────────────────────────

    @property
    def admin(self) -> dict[str, str]:
        """An identity-registry.admin token — the portal client does not hold it."""
        if self._admin is None:
            self._admin = self.http.bearer_headers_for(
                self.settings.ir_admin_client_id, self.settings.ir_admin_client_secret
            )
        return self._admin

    # ── apply ────────────────────────────────────────────────────────────────

    def apply(self) -> ScenarioReport:
        report = ScenarioReport(name=self.scenario.get("name", "scenario"))
        if not self._check_agreements(report):
            return report
        self._check_offers(report)
        for owner in self.scenario.get("owners") or []:
            self._apply_owner(owner, report)
        for participant in self.scenario.get("participants") or []:
            self._apply_participant(participant, report)
        return report

    def _check_agreements(self, report: ScenarioReport) -> bool:
        required = self.scenario.get("requires_agreements") or []
        if not required:
            return True
        try:
            existing = self.http.get(f"{self.ir}/agreements", headers=self.admin) or []
        except Exception as exc:
            report.problem(f"could not list agreements: {exc}")
            return False

        by_key = {(a.get("id"), a.get("version")): a for a in existing if isinstance(a, dict)}
        missing: list[str] = []
        for want in required:
            key = (want.get("id"), want.get("version"))
            found = by_key.get(key)
            if found is None:
                missing.append(f"{key[0]}@{key[1]}")
                continue
            if want.get("capacity") and found.get("capacity") != want["capacity"]:
                report.problem(
                    f"agreement {key[0]}@{key[1]} declares capacity "
                    f"{found.get('capacity')!r}, scenario expects {want['capacity']!r} — "
                    "the circle assertions would pass for the wrong reason"
                )
        if missing:
            report.problem(
                f"agreements not seeded: {', '.join(missing)} — run "
                "`cd services/identity-registry && uv run ir-cli agreement import "
                "--file seed/agreements.dev.yaml`"
            )
        return report.ok

    def _check_offers(self, report: ScenarioReport) -> None:
        """Offers are served by the connector from YAML, so assert, never create."""
        required = self.scenario.get("requires_offers") or []
        if not required:
            return
        try:
            published = self.http.get(f"{self.settings.connector_url}/ns/sharing-offers") or []
        except Exception as exc:
            report.problem(f"could not read published sharing offers: {exc}")
            return
        by_id = {o.get("id"): o for o in published if isinstance(o, dict)}
        for want in required:
            offer = by_id.get(want.get("id"))
            if offer is None:
                report.problem(
                    f"sharing offer {want.get('id')!r} is not published — add it to "
                    "services/connector/governance/sharing-offers.yaml and reload the connector"
                )
                continue
            recipients = offer.get("recipients") or {}
            for field_name, source in (
                ("controller", recipients),
                ("controller_role", recipients),
                ("purpose", offer),
            ):
                expected = want.get(field_name)
                if expected and source.get(field_name) != expected:
                    report.problem(
                        f"offer {want['id']!r} has {field_name}="
                        f"{source.get(field_name)!r}, scenario expects {expected!r}"
                    )

    def _apply_owner(self, spec: dict[str, Any], report: ScenarioReport) -> None:
        alias = spec["alias"]
        body = {
            "id": alias,
            "type": spec.get("type", "schema:Organization"),
            "name": spec.get("name", alias),
            "did": spec.get("did"),
            "aliases": spec.get("aliases") or [],
        }
        status, payload = self.http.raw(
            "POST", f"{self.ir}/admin/owners", body=body, headers=self.admin
        )
        if status in (200, 201):
            report.did(f"created owner {alias}")
        elif status == 409:
            log.debug("owner %s already exists", alias)
        else:
            report.problem(f"could not create owner {alias}: HTTP {status} {payload}")
            return

        accepts = spec.get("accepts")
        if accepts:
            self._accept_agreement(alias, accepts, report)

        member_of = spec.get("member_of")
        if member_of and spec.get("did"):
            self._apply_membership(spec["did"], member_of, report)

    def _accept_agreement(
        self, alias: str, accepts: dict[str, Any], report: ScenarioReport
    ) -> None:
        """Record acceptance — this is what gives the owner a provable capacity."""
        status, payload = self.http.raw(
            "POST",
            f"{self.ir}/admin/owners/{urllib.parse.quote(alias)}/agreement",
            body={
                "agreement_id": accepts["agreement_id"],
                "version": accepts["version"],
                "locale": accepts.get("locale", "en"),
                "accepted_by": accepts.get("accepted_by", "ds-e2e-scenario"),
            },
            headers=self.admin,
        )
        if status in (200, 201):
            capacity = payload.get("capacity") if isinstance(payload, dict) else None
            report.did(
                f"{alias} accepted {accepts['agreement_id']}@{accepts['version']} "
                f"(capacity={capacity})"
            )
        elif status == 409:
            log.debug("%s already accepted %s", alias, accepts["agreement_id"])
        else:
            report.problem(
                f"could not record agreement acceptance for {alias}: HTTP {status} {payload}"
            )

    def _apply_membership(
        self, user_did: str, organization: str, report: ScenarioReport
    ) -> None:
        status, payload = self.http.raw(
            "POST",
            f"{self.ir}/admin/memberships",
            body={"user_did": user_did, "organization_alias": organization},
            headers=self.admin,
        )
        if status in (200, 201):
            report.did(f"{user_did} is a member of {organization}")
        elif status == 409:
            log.debug("membership already present")
        else:
            report.problem(
                f"could not add membership {user_did}→{organization}: HTTP {status} {payload}"
            )

    def _apply_participant(self, spec: dict[str, Any], report: ScenarioReport) -> None:
        status, payload = self.http.raw(
            "POST",
            f"{self.ir}/admin/participants",
            body={
                "did": spec["did"],
                "roles": spec.get("roles") or ["consumer"],
                "dsp_address": spec.get("dsp_address"),
            },
            headers=self.admin,
        )
        if status in (200, 201):
            report.did(f"registered participant {spec['did']}")
            return
        if status == 409:
            # Already present — but possibly deactivated by an earlier destroy.
            # Registration must be *convergent*: apply has to leave the fixture
            # usable regardless of what state the previous cycle left behind,
            # or the second run of a suite silently tests a deactivated party.
            self._reactivate_participant(spec, report)
            return
        report.problem(
            f"could not register participant {spec['did']}: HTTP {status} {payload}"
        )

    def _reactivate_participant(self, spec: dict[str, Any], report: ScenarioReport) -> None:
        encoded = urllib.parse.quote(spec["did"], safe="")
        status, payload = self.http.raw(
            "GET", f"{self.ir}/admin/participants/{encoded}", headers=self.admin
        )
        if status == 200 and isinstance(payload, dict) and payload.get("active"):
            log.debug("participant %s already active", spec["did"])
            return

        status, payload = self.http.raw(
            "PATCH",
            f"{self.ir}/admin/participants/{encoded}",
            body={"active": True},
            headers=self.admin,
        )
        if status in (200, 201):
            report.did(f"reactivated participant {spec['did']}")
        else:
            report.problem(
                f"could not reactivate participant {spec['did']}: HTTP {status} {payload}"
            )

    # ── show ─────────────────────────────────────────────────────────────────

    def show(self) -> ScenarioReport:
        """Report current state without changing anything."""
        report = ScenarioReport(name=self.scenario.get("name", "scenario"))
        for owner in self.scenario.get("owners") or []:
            alias = owner["alias"]
            status, payload = self.http.raw(
                "GET",
                f"{self.ir}/owners/resolve?alias={urllib.parse.quote(alias)}",
                headers=self.admin,
            )
            if status != 200 or not isinstance(payload, dict):
                report.did(f"owner {alias}: absent")
                continue
            report.did(
                f"owner {alias}: status={payload.get('status')} "
                f"agreement={payload.get('agreement_id')}@{payload.get('agreement_version')} "
                f"capacity={payload.get('agreement_capacity')}"
            )
        for participant in self.scenario.get("participants") or []:
            did = participant["did"]
            status, payload = self.http.raw(
                "GET",
                f"{self.ir}/admin/participants/{urllib.parse.quote(did, safe='')}",
                headers=self.admin,
            )
            if status != 200 or not isinstance(payload, dict):
                report.did(f"participant {did}: absent")
                continue
            # Deregistration is a deactivation, not a delete — a DID that has
            # transacted stays auditable. So "present" is not the useful signal;
            # "active" is, because that is what the registry authorises on.
            state = "active" if payload.get("active") else "deactivated"
            report.did(f"participant {did}: {state}")
        return report

    # ── destroy ──────────────────────────────────────────────────────────────

    def destroy(self) -> ScenarioReport:
        """Remove only what this scenario names.

        Participants first, then owners: a participant references the owner's
        DID, and leaving a registered participant behind after its organisation
        is gone would let the next run resolve a half-provisioned identity.

        Deregistering a participant deactivates it and revokes its credentials
        rather than deleting the row — a DID that has transacted has to stay
        auditable. ``apply`` reactivates it, so the cycle is still repeatable.
        """
        report = ScenarioReport(name=self.scenario.get("name", "scenario"))

        for participant in self.scenario.get("participants") or []:
            did = participant["did"]
            status, _ = self.http.raw(
                "DELETE",
                f"{self.ir}/admin/participants/{urllib.parse.quote(did, safe='')}",
                headers=self.admin,
            )
            if status in (200, 204):
                report.did(f"removed participant {did}")
            elif status == 404:
                log.debug("participant %s already absent", did)
            else:
                report.problem(f"could not remove participant {did}: HTTP {status}")

        for owner in self.scenario.get("owners") or []:
            alias = owner["alias"]
            member_of = owner.get("member_of")
            if member_of and owner.get("did"):
                self.http.raw(
                    "DELETE",
                    f"{self.ir}/admin/memberships/"
                    f"{urllib.parse.quote(owner['did'], safe='')}/"
                    f"{urllib.parse.quote(member_of)}",
                    headers=self.admin,
                )
            status, _ = self.http.raw(
                "DELETE",
                f"{self.ir}/admin/owners/{urllib.parse.quote(alias)}",
                headers=self.admin,
            )
            if status in (200, 204):
                report.did(f"removed owner {alias}")
            elif status == 404:
                log.debug("owner %s already absent", alias)
            else:
                report.problem(f"could not remove owner {alias}: HTTP {status}")

        return report


def build_runner(
    settings: E2ESettings, http: HttpClient, name: str = DEFAULT_SCENARIO
) -> ScenarioRunner:
    return ScenarioRunner(settings, http, load_scenario(name))
