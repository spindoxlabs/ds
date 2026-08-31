"""The API surface, read from each service's own OpenAPI document.

`api_contract` sweeps every route for correct refusal. Which routes those are
used to be a literal table in the flow, one line per route, kept by hand beside
the routers it mirrored. Measured against the four apps it claimed to cover, it
had drifted to **70 of 110** guarded routes (`E2E-03`) — and the shape of the
gap says why a longer table is not the fix: four of the six missing connector
routes were the *item* under a collection that was already probed, so whoever
added the pair probed the one they happened to be looking at.

That is the same defect `E2E-14` fixed one level up in this same file, by
deriving the health gate from the routes instead of listing the services beside
them. This module is that fix applied to the table itself.

**The source of truth is the app.** `ds_auth.require_permission` registers a
`DataspacePermission` security scheme, so every guarded operation carries
``security: [{"DataspacePermission": ["connector.provider.read", …]}]`` in the
document the service publishes at ``/openapi.json``. Two things follow that the
harness previously had to be told:

* a route is guarded because the running app says so, not because someone
  remembered to add a line;
* the permissions a route accepts are published, so the under-privileged token
  the sweep replays can be checked against them rather than against a hardcoded
  set of exceptions that had gone stale.

**A route absent from the document is absent from the sweep.** That is the one
weakness of deriving from OpenAPI rather than from the route table itself, so
the answer is that no service hides one: `tests/test_route_inventory.py` fails
when any of the four declares ``include_in_schema=False``. There used to be a
hand-written list of the exceptions and a single entry in it,
`POST /consent/register-transfer` — the route is published now and the list is
gone. Hiding a route conceals it from readers of a document whose source is
public anyway, and turns a documentation decision into a security-sweep one.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# The security scheme `ds_auth.require_permission` registers on every route it
# guards. Second holder of a string owned by `ds_auth.fastapi`, because
# `libs/ds-e2e` deliberately does not depend on `libs/ds-auth` — a path
# dependency would rebuild this package on every auth change for one constant.
# `test_route_inventory.py` reads the name out of `ds_auth`'s source and fails
# when the two disagree, which is the check that makes the copy safe.
PERMISSION_SCHEME = "DataspacePermission"

# Substituted for a path parameter when a template is turned into a probe. It
# has to be a value no route resolves to something real, and no sibling route
# claims as a literal segment: `/admin/participants/{did}` must not probe
# `/admin/participants/check`.
PATH_PARAM = "e2e-nonexistent"

_PARAM = re.compile(r"\{[^}]+\}")


@dataclass(frozen=True)
class Route:
    """One operation of one service, as the service describes it."""

    service: str
    method: str
    template: str
    #: None when the app publishes no `DataspacePermission` requirement.
    #: An empty tuple is impossible — the guard always names at least one.
    permissions: tuple[str, ...] | None = None

    @property
    def guarded(self) -> bool:
        """Whether the app declares this route behind a permission guard.

        Not the same as "refuses an anonymous caller": the subject-facing
        `/consent/my/*` routes authenticate on a VC-JWT and the DCP endpoints on
        the protocol's own credentials, so both are unguarded *here* and still
        refuse. The sweep asserts refusal for every route that is not declared
        public, and reserves the bearer-token battery for these.
        """
        return self.permissions is not None

    @property
    def path(self) -> str:
        """A concrete path to probe, with every parameter filled in."""
        return _PARAM.sub(PATH_PARAM, self.template)

    @property
    def label(self) -> str:
        return f"{self.service} {self.method} {self.template}"

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.service, self.method, self.template)


def routes_from_openapi(service: str, spec: Mapping[str, Any]) -> list[Route]:
    """Every operation the document describes, with its published permissions.

    Unknown verbs (`trace`, and the `parameters` key OpenAPI allows beside the
    operations) are skipped rather than probed as methods.
    """
    methods = {"get", "post", "put", "patch", "delete"}
    routes: list[Route] = []
    paths = spec.get("paths") or {}
    if not isinstance(paths, Mapping):
        return routes
    for template, operations in paths.items():
        if not isinstance(operations, Mapping):
            continue
        for verb, operation in operations.items():
            if verb.lower() not in methods or not isinstance(operation, Mapping):
                continue
            routes.append(
                Route(
                    service=service,
                    method=verb.upper(),
                    template=template,
                    permissions=_published_permissions(operation),
                )
            )
    routes.sort(key=lambda r: (r.template, r.method))
    return routes


def _published_permissions(operation: Mapping[str, Any]) -> tuple[str, ...] | None:
    for requirement in operation.get("security") or []:
        if isinstance(requirement, Mapping) and PERMISSION_SCHEME in requirement:
            return tuple(requirement[PERMISSION_SCHEME] or ())
    return None


def token_scopes(access_token: str) -> frozenset[str]:
    """The `scope` claim of a JWT, read without verifying it.

    The harness is not the audience of this token and is not deciding anything
    with it — it is asking *what did the realm actually grant this client*, so
    that the wrong-scope battery can tell a route the client legitimately holds
    from one it must be refused. Reading the claim is the only way to ask the
    realm rather than a comment: the hardcoded answer that preceded it drifted
    from what the realm granted, and nothing said so.

    An unreadable token yields an empty set, which is the safe direction: no
    route is excused, so the battery over-probes rather than under-probes.
    """
    parts = access_token.split(".")
    if len(parts) < 2:
        return frozenset()
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return frozenset()
    scope = claims.get("scope") if isinstance(claims, Mapping) else None
    if not isinstance(scope, str):
        return frozenset()
    return frozenset(scope.split())


def routes_held_by(routes: Iterable[Route], scopes: frozenset[str]) -> list[Route]:
    """The routes a token holding `scopes` may legitimately reach.

    A route accepts any one of its published permissions, so an intersection is
    the whole rule. `{service}.admin` needs no special case: a route that admits
    it publishes it beside the finer permission, because
    `require_permission("connector.provider.read", "connector.admin")` names
    both — and `require_exact_permission` names only what it means, which is
    exactly why admin does not satisfy it.
    """
    return [r for r in routes if r.permissions and scopes.intersection(r.permissions)]
