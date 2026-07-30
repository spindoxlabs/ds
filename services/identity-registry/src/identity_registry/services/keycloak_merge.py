"""Merge ds's core client declaration with its domain overlays.

`services/keycloak/clients.yaml` declares what **ds** needs from a realm.
`clients.<domain>.yaml` declares what the **domain backend deployed alongside it**
needs from the same realm. Two statements, applied by different deployments:

============================  ==============================  ====================
                              posture A (ds owns the realm)   posture B (guest)
============================  ==============================  ====================
core ``clients.yaml``         applied                         mirrored across
``clients.<domain>.yaml``     applied                         **omitted**
============================  ==============================  ====================

**Why merge rather than pass two files to the sync.** Verified against
`celine-policies`, the CLI that syncs both realms:

* It takes exactly one file — ``config_path`` is ``dir_okay=False`` and the load
  is a single ``yaml.safe_load``. No include, no merge, no repeatable ``--config``.
* ``--prune`` is opt-in and guards only orphan *scopes* and *clients*, so a split
  file will not delete them.
* But **scope assignments and audience mappers are recomputed and removed
  unconditionally**, outside the prune branch, for every client present in the
  synced file. So syncing a core file from which ``rec-registry.lookup`` has moved
  does not delete the scope — it **strips the grant from `svc-ds-dataset-api`**,
  silently, with no flag involved. The data-plane symptom is a row filter that
  resolves nobody.

A client absent from the synced file altogether is untouched (it is an orphan, and
orphans need ``--prune``), which is why moving `svc-rec-registry` out is safe and
moving a *grant on a client that stays* is not. That asymmetry is the whole reason
this module exists.

What an overlay may do
----------------------

**Add** scopes, **add** clients, and **widen** a core client's ``default_scopes`` /
``optional_scopes`` / ``extra_audiences``. It may not redefine a core client's
identity (``secret``, ``scopes_prefix``, ``name``) or set a realm-level key. An
overlay is a domain backend asking for grants; letting it restate ds's own clients
would make it a second, unreviewable copy of the authority file.

    ir-cli keycloak merge --overlay energy      # write the effective file
    ir-cli keycloak merge --overlay energy --check
    ir-cli keycloak merge --overlay energy --stdout
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

# …/services/identity-registry/src/identity_registry/services/ → repo root
REPO = Path(__file__).resolve().parents[5]
KEYCLOAK = REPO / "services" / "keycloak"
SOURCE = KEYCLOAK / "clients.yaml"
TARGET = KEYCLOAK / "clients.effective.yaml"

#: Generated artefacts that live beside the overlays and are not overlays.
#: Named rather than pattern-matched — a new generated file that quietly became
#: an overlay would widen a realm by accident.
GENERATED = {TARGET.name, "clients.host.generated.yaml"}

#: Realm-level keys an overlay may not set. Which realm ds talks to, and which
#: client humans log in through, are ds's statements about the deployment.
CORE_ONLY_KEYS = frozenset({"realm", "oauth2_proxy_client"})

#: The only keys an overlay may carry on a client that already exists in the core.
AUGMENTABLE_KEYS = frozenset(
    {"client_id", "default_scopes", "optional_scopes", "extra_audiences"}
)

#: Keys an overlay file may carry at the top level.
OVERLAY_KEYS = frozenset({"overlay", "scopes", "clients"})

MERGE_KEYS = ("default_scopes", "optional_scopes", "extra_audiences")


class MergeError(Exception):
    """An overlay asked for something an overlay may not do."""


def overlay_path(name: str, directory: Path | None = None) -> Path:
    return (directory or KEYCLOAK) / f"clients.{name}.yaml"


def discover_overlays(directory: Path | None = None) -> list[str]:
    """Overlay names present on disk, generated artefacts excluded."""
    directory = directory or KEYCLOAK
    return sorted(
        path.name[len("clients.") : -len(".yaml")]
        for path in directory.glob("clients.*.yaml")
        if path.name not in GENERATED
    )


def load_overlays(
    names: list[str], directory: Path | None = None
) -> list[tuple[str, dict]]:
    """Load the named overlays, **failing on a missing one**.

    A silently-thinner realm is the failure mode this whole mechanism exists to
    prevent, so a deployment that names an overlay it does not have gets an error
    rather than a core-only sync.
    """
    loaded: list[tuple[str, dict]] = []
    for name in names:
        path = overlay_path(name, directory)
        if not path.exists():
            available = discover_overlays(directory)
            raise MergeError(
                f"overlay '{name}' not found at {path} — "
                f"available: {', '.join(available) or 'none'}"
            )
        loaded.append((name, yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    return loaded


def _merge_scopes(merged: dict, name: str, overlay: dict) -> None:
    declared = {s["name"] for s in merged.get("scopes") or []}
    for scope in overlay.get("scopes") or []:
        if scope["name"] in declared:
            raise MergeError(
                f"overlay '{name}' redeclares scope {scope['name']}, which the core "
                "already declares — a scope has exactly one definition"
            )
        merged.setdefault("scopes", []).append(copy.deepcopy(scope))
        declared.add(scope["name"])


def _augment_client(name: str, target: dict, entry: dict) -> None:
    illegal = sorted(set(entry) - AUGMENTABLE_KEYS)
    if illegal:
        raise MergeError(
            f"overlay '{name}' sets {illegal} on core client {entry['client_id']} — "
            "an overlay may only add grants and audiences to a client the core owns"
        )
    for key in MERGE_KEYS:
        additions = entry.get(key) or []
        if not additions:
            continue
        existing = target.setdefault(key, [])
        for value in additions:
            if value not in existing:
                existing.append(value)


def _merge_clients(merged: dict, name: str, overlay: dict) -> None:
    by_id = {c["client_id"]: c for c in merged.get("clients") or []}
    for entry in overlay.get("clients") or []:
        client_id = entry["client_id"]
        target = by_id.get(client_id)
        if target is None:
            new = copy.deepcopy(entry)
            merged.setdefault("clients", []).append(new)
            by_id[client_id] = new
        else:
            _augment_client(name, target, entry)


def merge(core: dict, overlays: list[tuple[str, dict]]) -> dict:
    """The effective declaration: core, widened by each overlay in order."""
    merged = copy.deepcopy(core)
    for name, overlay in overlays:
        unknown = sorted(set(overlay) - OVERLAY_KEYS)
        if unknown:
            reserved = sorted(set(unknown) & CORE_ONLY_KEYS)
            detail = (
                f"{reserved} is the core's to declare"
                if reserved
                else f"unknown top-level key(s) {unknown}"
            )
            raise MergeError(f"overlay '{name}': {detail}")
        _merge_scopes(merged, name, overlay)
        _merge_clients(merged, name, overlay)
    return merged


def validate(document: dict) -> list[str]:
    """Grants that name a scope nobody declares.

    This is the mistake the split makes possible: leaving a grant in the core
    while its scope moves to an overlay. `celine-policies` assigns scopes by name
    and would fail — or worse, skip — at sync time, in a container whose log
    nobody reads.
    """
    declared = {s["name"] for s in document.get("scopes") or [] if s.get("name")}
    problems: list[str] = []
    for client in document.get("clients") or []:
        for key in ("default_scopes", "optional_scopes"):
            for scope in client.get(key) or []:
                if scope not in declared:
                    problems.append(
                        f"{client['client_id']}: {key} names undeclared scope {scope}"
                    )
    return problems


def render(merged: dict, overlay_names: list[str]) -> str:
    applied = ", ".join(overlay_names) if overlay_names else "(none)"
    header = f"""\
# GENERATED FILE — DO NOT EDIT.
#
# Source:     services/keycloak/clients.yaml
# Overlays:   {applied}
# Regenerate: task keycloak:merge
#
# The **effective** realm declaration: what ds needs, widened by the domain
# backends this deployment runs. `keycloak-sync` applies this file rather than the
# core one, because `celine-policies keycloak sync` takes a single file and
# recomputes each client's grants from it — syncing the core alone would strip an
# overlay's grants off a client the core also declares, with no flag involved.
#
# Change the core or an overlay, then regenerate. Editing this file is editing the
# output.
"""
    body = yaml.safe_dump(merged, sort_keys=False, allow_unicode=True, width=100)
    return header + "\n" + body


def build(overlay_names: list[str], directory: Path | None = None) -> str:
    """Load, merge, validate and render — the whole pipeline, for callers."""
    directory = directory or KEYCLOAK
    core = yaml.safe_load((directory / "clients.yaml").read_text(encoding="utf-8"))
    merged = merge(core, load_overlays(overlay_names, directory))
    problems = validate(merged)
    if problems:
        raise MergeError(
            "the merged declaration is inconsistent:\n  " + "\n  ".join(problems)
        )
    return render(merged, overlay_names)
