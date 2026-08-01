"""Generate the ds section of a host realm's `clients.yaml`.

ds's `services/keycloak/clients.yaml` is the **declaration of what ds needs from a
realm**. Where ds owns the realm it is applied directly. Where ds is a guest — the
celine deployment — the host's `clients.yaml` must carry the same clients and
scopes, and it has been hand-maintained: every row of drift found so far
(`svc-edc` missing `connector.internal`, `svc-ds-provenance` undeclared,
`svc-ds-portal` holding `connector.admin`) is a symptom of two files edited by
hand and compared by eye.

So the host's copy is generated from ds's, and the check becomes a no-diff test
rather than a review.

**Two carve-outs, both deliberate:**

* `svc-ds-e2e` never crosses. It is dev/CI only and deliberately over-granted, and
  a test identity in a production realm is a permanent credential nobody audits.
* `*.admin` is dropped on the way across. Admin is an *operator* grant — a superset
  satisfying every `{service}.*` — and a long-lived process should never hold one.
  ds already applies this rule to its own service clients; applying it here stops a
  copy from quietly widening what the original granted.

A client whose grants are *entirely* admin still crosses, with an empty
`default_scopes`: provisioned-but-unused is harmless, missing is a 403 at the worst
possible moment.

**The domain overlay does not cross either, and it is excluded by construction:**
this generator reads the *core* `clients.yaml`, never the merged effective file
(`keycloak_merge.py`). In a host realm `rec-registry.*` and `svc-rec-registry` are
the host's own services — declared by the host, on the host's terms — so a mirror
that asked for them would be ds claiming authority over another project's
vocabulary. Reading the core file is therefore the correctness property, not a
shortcut: the two generators consume the same source and split on a boundary that
is written down in one place.

    ir-cli keycloak mirror                 # write the fragment
    ir-cli keycloak mirror --check         # fail if it is stale
    ir-cli keycloak mirror --diff <host clients.yaml>

Lives here rather than in a loose script because `ir-cli` already owns this
surface — `keycloak map-user`, `keycloak org-sync` — is installed in the
identity-registry image, and is how the realm provisioning chain is already
driven. A standalone script had no packaging, no declared dependency and no
import path a test could use.
"""
from __future__ import annotations

from pathlib import Path

import yaml

# …/services/identity-registry/src/identity_registry/services/ → repo root
REPO = Path(__file__).resolve().parents[5]
SOURCE = REPO / "services" / "keycloak" / "clients.yaml"
TARGET = REPO / "services" / "keycloak" / "clients.host.generated.yaml"

EXCLUDED_CLIENTS = {"svc-ds-e2e"}

HEADER = """\
# GENERATED FILE — DO NOT EDIT.
#
# Source: services/keycloak/clients.yaml
# Regenerate: task keycloak:mirror
#
# The ds section of a *host* realm's clients.yaml, for a deployment where ds is a
# guest rather than the realm's owner. Merge these entries into the host's file;
# everything else there is the host's own and is left alone.
#
# `svc-ds-e2e` is excluded (dev/CI only, deliberately over-granted) and every
# `*.admin` grant is dropped: admin is an operator grant, and a long-lived process
# should not hold a superset over every permission of a service.
"""


def _is_admin(scope: str) -> bool:
    return scope.endswith(".admin")


def build_mirror(source: dict) -> dict:
    """The subset of ds's declaration a host realm must carry."""
    scopes = [
        {"name": s["name"], "description": s.get("description", "")}
        for s in source.get("scopes") or []
        if not _is_admin(s["name"])
    ]

    clients = []
    for client in source.get("clients") or []:
        if client["client_id"] in EXCLUDED_CLIENTS:
            continue
        entry = {
            "client_id": client["client_id"],
            "name": client.get("name", client["client_id"]),
            "secret": client.get("secret", ""),
            "default_scopes": [
                s for s in (client.get("default_scopes") or []) if not _is_admin(s)
            ],
        }
        if client.get("scopes_prefix"):
            entry["scopes_prefix"] = client["scopes_prefix"]
        if client.get("extra_audiences"):
            entry["extra_audiences"] = list(client["extra_audiences"])
        # Without this the host creates the client with no service account, and
        # every client_credentials grant against it fails. It is declared on
        # exactly the clients that authenticate as themselves, so dropping it
        # mirrors a client that cannot do the one thing it exists to do.
        if client.get("service_account_enabled"):
            entry["service_account_enabled"] = True
        clients.append(entry)

    return {"scopes": scopes, "clients": clients}


def render(source: dict) -> str:
    mirror = build_mirror(source)
    body = yaml.safe_dump(mirror, sort_keys=False, allow_unicode=True, width=100)
    return HEADER + "\n" + body


def diff_against_host(source: dict, host_path: Path) -> list[str]:
    """What the host realm is missing. Empty means the host is a superset.

    Reported rather than written: the host's file belongs to the host, and a tool
    that edits another repository's config is a tool nobody can review.
    """
    host = yaml.safe_load(host_path.read_text(encoding="utf-8")) or {}
    mirror = build_mirror(source)

    host_scopes = {s["name"] for s in host.get("scopes") or []}
    host_clients = {c["client_id"]: c for c in host.get("clients") or []}

    problems: list[str] = []
    for scope in mirror["scopes"]:
        if scope["name"] not in host_scopes:
            problems.append(f"scope missing: {scope['name']}")

    for client in mirror["clients"]:
        cid = client["client_id"]
        if cid not in host_clients:
            problems.append(f"client missing: {cid}")
            continue
        have = set(host_clients[cid].get("default_scopes") or [])
        for scope in client["default_scopes"]:
            if scope not in have:
                problems.append(f"{cid}: missing grant {scope}")
        for scope in sorted(s for s in have if _is_admin(s)):
            problems.append(
                f"{cid}: holds {scope} — an operator grant on a service client"
            )
    return problems
