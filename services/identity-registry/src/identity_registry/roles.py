"""Role modes — which half of this service a given instance is (`DID-04`).

One image, two roles. A **trust anchor** is the governance authority's instance:
it issues credentials, holds the participant/owner/membership registries, runs
the StatusList and takes organisation applications. A **participant** instance
belongs to one organisation and serves only what a holder serves — its own DID
documents, its own STS, its own credential service.

Why a role and not two services: the code is the same, the difference is which
routes are mounted and which data exists. Two deployables would duplicate the
crypto, the DID resolution and the schema, and then drift.

## Two mechanisms, deliberately

`ROUTERS` decides what gets **mounted**. `PATH_ROLES` independently classifies
every **path** the service can serve. `audit()` compares them and startup fails
on any disagreement. That redundancy is the point — it is the `T-4` shape, the
one kind of check that fails because of something a change *did not* do:

- add a route to an existing router whose path does not fit that router's role
  (a `/admin/...` path on a participant-mounted router) → caught;
- add a whole router and mount it without classifying its paths → caught;
- classify a path and forget to mount its router → caught.

A test asserting the same thing could only assert what someone remembered to
write down. This runs against the routes that actually exist, in the process
that actually serves them.

## What is *not* asserted here, and why

The plan's phrasing was *"a participant instance exposes no anchor route and
vice versa"*. Only the first half is a route question. The second half —
**should the anchor stop serving `/sts` and presentation queries?** — cannot be
answered by removing routes today: until `DID-05` splits the deployment, the
anchor is the STS and credential service for every participant, and mounting it
role-strict would take the dev stack down. That is the `IR-10` trap: *a guard
needs a supply path in the same change.*

So the anchor keeps those routes, and what narrows is the **data** — after
`DID-06`/`DID-09` it holds no private key but its own, so it can answer for
nothing but itself. `DID-12` is the invariant that asserts it, and it belongs
there rather than here because it is a fact about custody, not about routing.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter

from .api.v1.admin import router as admin_router
from .api.v1.agreements import router as agreements_router
from .api.v1.credentials import check_router as credential_check_router
from .api.v1.credentials import router as presentations_router
from .api.v1.issuer import router as issuer_router
from .api.v1.memberships import router as memberships_router
from .api.v1.onboarding import admin_router as onboarding_admin_router
from .api.v1.onboarding import public_router as onboarding_public_router
from .api.v1.organizations import router as organizations_router
from .api.v1.owners import router as owners_router
from .api.v1.public import did_router, status_router, trust_router
from .api.v1.sts import router as sts_router
from .api.v1.users import router as users_router

TRUST_ANCHOR = "trust-anchor"
PARTICIPANT = "participant"

ROLES = frozenset({TRUST_ANCHOR, PARTICIPANT})

#: Served whatever the role is.
BOTH = frozenset(ROLES)
#: The governance authority's own surface.
ANCHOR_ONLY = frozenset({TRUST_ANCHOR})
#: A holder's surface. Nothing is participant-only *yet* — see the module
#: docstring on why the anchor keeps the holder routes until `DID-12`.
HOLDER = frozenset(ROLES)


@dataclass(frozen=True, slots=True)
class RouterSpec:
    """One mountable router and the roles that serve it."""

    name: str
    router: APIRouter
    roles: frozenset[str]

    def paths(self) -> list[str]:
        """The full paths this router serves.

        `APIRouter` applies its own prefix when a route is registered, so
        `route.path` is already `/credentials/check` and prepending
        `router.prefix` again yields `/credentials/credentials/check` — which
        classifies under `/credentials`, passes the audit, and means the audit
        was checking paths nobody serves. Found by
        `test_a_stale_classification_entry_is_visible`, which is the whole
        reason that test exists.
        """
        return [r.path for r in self.router.routes if hasattr(r, "path")]


#: The single source of what a given role mounts. Order is mount order, and it
#: matters twice: `credential_check_router` before `presentations_router`
#: (`/check` versus `{did:path}`), and `did_router` last of all — its
#: `/{did_path}/did.json` is a catch-all.
ROUTERS: tuple[RouterSpec, ...] = (
    RouterSpec("credentials.check", credential_check_router, ANCHOR_ONLY),
    RouterSpec("credentials.presentations", presentations_router, HOLDER),
    RouterSpec("sts", sts_router, HOLDER),
    RouterSpec("users", users_router, BOTH),
    RouterSpec("admin", admin_router, ANCHOR_ONLY),
    RouterSpec("memberships", memberships_router, ANCHOR_ONLY),
    RouterSpec("organizations", organizations_router, ANCHOR_ONLY),
    RouterSpec("agreements", agreements_router, ANCHOR_ONLY),
    RouterSpec("owners", owners_router, ANCHOR_ONLY),
    RouterSpec("issuer", issuer_router, ANCHOR_ONLY),
    RouterSpec("onboarding.admin", onboarding_admin_router, ANCHOR_ONLY),
    RouterSpec("onboarding.public", onboarding_public_router, ANCHOR_ONLY),
    RouterSpec("status", status_router, ANCHOR_ONLY),
    RouterSpec("trust", trust_router, ANCHOR_ONLY),
    RouterSpec("dids", did_router, BOTH),
)

#: Independent classification, by path prefix, longest first. This is the half
#: that catches a route added to a router whose role it does not share.
#:
#: `/{did_path}/did.json` is last because it matches everything; a path that
#: reaches it has already failed every more specific entry, which is exactly the
#: behaviour the router ordering relies on.
PATH_ROLES: tuple[tuple[str, frozenset[str]], ...] = (
    ("/health", BOTH),
    ("/admin", ANCHOR_ONLY),
    ("/onboarding", ANCHOR_ONLY),
    ("/issuer", ANCHOR_ONLY),
    ("/agreements", ANCHOR_ONLY),
    ("/memberships", ANCHOR_ONLY),
    ("/owners", ANCHOR_ONLY),
    ("/status", ANCHOR_ONLY),
    ("/trust", ANCHOR_ONLY),
    ("/credentials/check", ANCHOR_ONLY),
    ("/credentials", HOLDER),
    ("/sts", HOLDER),
    ("/users", BOTH),
    ("/dids", BOTH),
    ("/.well-known/did.json", BOTH),
    ("/{did_path}/did.json", BOTH),
)


class RoleConfigurationError(RuntimeError):
    """The mounted routes and the path classification disagree."""


def normalize_role(value: str) -> str:
    role = (value or "").strip().lower()
    if role not in ROLES:
        raise RoleConfigurationError(
            f"IDENTITY_REGISTRY_ROLE={value!r} is not a role. "
            f"Use one of: {', '.join(sorted(ROLES))}."
        )
    return role


def _strip_converters(path: str) -> str:
    """`/{did:path}/token` → `/{did}/token`.

    A router declares `{did:path}`; OpenAPI and every doc write `{did}`. The
    table is written the way a person reads it, and both forms classify the same
    — otherwise the catch-all `/{did_path:path}/did.json` would have to appear
    twice, and one of the two copies would eventually be the stale one.
    """
    out = path
    for converter in (":path", ":str", ":int", ":uuid", ":float"):
        out = out.replace(converter + "}", "}")
    return out


def roles_for_path(path: str) -> frozenset[str] | None:
    """The roles allowed to serve *path*, or ``None`` if it is unclassified.

    Longest prefix wins, so `/credentials/check` beats `/credentials` regardless
    of table order — the ordering in `PATH_ROLES` is for the reader.
    """
    path = _strip_converters(path)
    best: tuple[int, frozenset[str]] | None = None
    for prefix, roles in PATH_ROLES:
        if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), roles)
    return best[1] if best else None


def specs_for_role(role: str) -> tuple[RouterSpec, ...]:
    return tuple(spec for spec in ROUTERS if role in spec.roles)


def audit(role: str, mounted_paths: list[str]) -> list[str]:
    """Every disagreement between what is mounted and what the role may serve.

    Returns **all** of them rather than the first — the same reason
    `ProductionGuard` and the connector's governance sync report in one pass: a
    reader fixing one violation should not have to restart to discover the next.
    """
    problems: list[str] = []

    for path in sorted(set(mounted_paths)):
        allowed = roles_for_path(path)
        if allowed is None:
            problems.append(
                f"{path} is mounted but not classified in roles.PATH_ROLES — "
                "add it, naming the role that may serve it"
            )
        elif role not in allowed:
            problems.append(
                f"{path} is mounted on a {role!r} instance but PATH_ROLES "
                f"restricts it to {', '.join(sorted(allowed))}"
            )

    mounted = set(mounted_paths)
    for spec in ROUTERS:
        if role not in spec.roles:
            continue
        for path in spec.paths():
            if path not in mounted:
                problems.append(
                    f"{path} is classified for {role!r} via router {spec.name!r} "
                    "but is not mounted"
                )

    return problems
