"""Emit the role-bundle table — and the reading of a token it implies — as TypeScript.

The portal gates its UI on the same permissions the API enforces, so it needs the
same expansion. Hand-writing a second copy of a *table* is worse than the
duplicated *matcher* that already exists: a matcher is one rule that can be
eyeballed, whereas a table drifts entry by entry and every drift is a page that
either hides an action the user may take or offers one the API will refuse.

It also needs the same **reading of the claims**. The portal used to carry its own
— realm roles plus every client's `resource_access` roles plus a flat merge of
realm and organisation groups — while the backend read groups only, so the two
disagreed about who an administrator was. The two levels (allowlisted realm roles;
each organisation's own groups) are therefore rendered here as code, not only the
table they consult.

So the Python module is the definition and the TypeScript is generated from it,
with a no-diff test (`tests/test_bundles_export.py`) making the checked-in copy a
build artifact rather than a document someone remembers to update, and a shared
case table (`tests/parity/authority-cases.json`) that both suites decide.

Regenerate with ``task -d libs/ds-auth bundles:generate``.
"""

from __future__ import annotations

from pathlib import Path

from .bundles import (
    MACHINE_IDENTITY_PERMISSIONS,
    ORGANISATION_BUNDLES,
    ORGANISATION_PERMISSIONS,
    PLATFORM_ADMIN_ROLE,
    PLATFORM_BUNDLES,
    REALM_ROLE_BUNDLES,
    ROLE_BUNDLES,
)

# Relative to the repository root.
PORTAL_TARGET = Path("services/portal/src/lib/server/bundles.generated.ts")

_HEADER = """\
// GENERATED FILE — DO NOT EDIT.
//
// Source: libs/ds-auth/src/ds_auth/bundles.py (+ the claim reading in
// ds_auth.jwt / ds_auth.principal, rendered by ds_auth/bundles_export.py)
// Regenerate: task -d libs/ds-auth bundles:generate
//
// The two levels a user token's authority comes from, mirroring `ds_auth`
// exactly: allowlisted realm roles (platform-wide) and each organisation's own
// groups (that organisation only). The portal gates its UI on the result; the
// backend re-authorizes every request against the same table, so a stale copy
// here shows the wrong buttons rather than granting anything.
"""


def _ts_string_array(values: tuple[str, ...] | list[str], indent: str) -> str:
    body = "".join(f"{indent}\t'{v}',\n" for v in values)
    return f"[\n{body}{indent}]"


def _ts_record(mapping: dict[str, str]) -> str:
    body = "".join(f"\t'{k}': '{mapping[k]}',\n" for k in sorted(mapping))
    return f"{{\n{body}}}"


def render_typescript() -> str:
    lines = [_HEADER, ""]

    lines.append("export const ROLE_BUNDLES: Record<string, string[]> = {")
    for bundle in sorted(ROLE_BUNDLES):
        lines.append(f"\t'{bundle}': {_ts_string_array(ROLE_BUNDLES[bundle], chr(9))},")
    lines.append("};")
    lines.append("")

    lines.append(
        "export const MACHINE_IDENTITY_PERMISSIONS: string[] = "
        f"{_ts_string_array(sorted(MACHINE_IDENTITY_PERMISSIONS), '')};"
    )
    lines.append("")
    lines.append(f"export const PLATFORM_ADMIN_ROLE = '{PLATFORM_ADMIN_ROLE}';")
    lines.append("")
    lines.append(
        "export const PLATFORM_BUNDLES: string[] = "
        f"{_ts_string_array(sorted(PLATFORM_BUNDLES), '')};"
    )
    lines.append("")
    lines.append(
        "export const ORGANISATION_BUNDLES: string[] = "
        f"{_ts_string_array(sorted(ORGANISATION_BUNDLES), '')};"
    )
    lines.append("")
    lines.append(
        "export const REALM_ROLE_BUNDLES: Record<string, string> = "
        f"{_ts_record(REALM_ROLE_BUNDLES)};"
    )
    lines.append("")
    lines.append(
        "export const ORGANISATION_PERMISSIONS: string[] = "
        f"{_ts_string_array(sorted(ORGANISATION_PERMISSIONS), '')};"
    )
    lines.append("")

    lines.append(_TS_FUNCTIONS)

    return "\n".join(lines)


_TS_FUNCTIONS = """\
type Claims = Record<string, unknown>;

function orderedUnique(values: Iterable<string>): string[] {
\tconst seen = new Set<string>();
\tconst out: string[] = [];
\tfor (const v of values) {
\t\tif (v && !seen.has(v)) {
\t\t\tseen.add(v);
\t\t\tout.push(v);
\t\t}
\t}
\treturn out;
}

/**
 * `realm_access.roles` — and nowhere else. Never `groups`, never a top-level
 * `roles`, never `resource_access.<client>.roles`. Twin of
 * `ds_auth.jwt.extract_realm_roles`.
 */
export function realmRoles(claims: Claims): string[] {
\tconst access = claims.realm_access;
\tif (!access || typeof access !== 'object' || Array.isArray(access)) return [];
\tconst roles = (access as Record<string, unknown>).roles;
\tif (!Array.isArray(roles)) return [];
\treturn orderedUnique(roles.filter((r): r is string => typeof r === 'string'));
}

/** The organisation aliases in the `organization` claim. */
export function organisationAliases(claims: Claims): string[] {
\tconst orgs = claims.organization;
\tif (!orgs || typeof orgs !== 'object' || Array.isArray(orgs)) return [];
\treturn Object.entries(orgs as Record<string, unknown>)
\t\t.filter(([, data]) => !!data && typeof data === 'object' && !Array.isArray(data))
\t\t.map(([alias]) => alias);
}

/**
 * The groups held **within** one organisation, leading slash stripped. Twin of
 * `ds_auth.models.Organization.groups`. `null` when not a member.
 */
export function organisationGroups(claims: Claims, alias: string): string[] | null {
\tconst orgs = claims.organization;
\tif (!orgs || typeof orgs !== 'object' || Array.isArray(orgs)) return null;
\tif (!Object.prototype.hasOwnProperty.call(orgs, alias)) return null;
\tconst data = (orgs as Record<string, unknown>)[alias];
\tif (!data || typeof data !== 'object' || Array.isArray(data)) return null;
\tconst groups = (data as Record<string, unknown>).groups;
\tif (!Array.isArray(groups)) return [];
\treturn groups
\t\t.filter((g): g is string => typeof g === 'string' && g.trim() !== '')
\t\t.map((g) => g.replace(/^\\/+/, ''));
}

/**
 * What allowlisted realm roles grant, deployment-wide. Twin of
 * `ds_auth.bundles.platform_authority`: a role not in `REALM_ROLE_BUNDLES`
 * grants nothing, and there is no pass-through at this level.
 */
export function platformAuthority(claims: Claims): string[] {
\tconst out: string[] = [];
\tfor (const role of realmRoles(claims)) {
\t\tconst bundle = REALM_ROLE_BUNDLES[role];
\t\tif (bundle) out.push(...ROLE_BUNDLES[bundle]);
\t}
\treturn orderedUnique(out);
}

/**
 * What one organisation's own groups grant, within it. Twin of
 * `ds_auth.bundles.organisation_authority`: a Layer B alias first, then an
 * organisation bundle expands, then a name in `ORGANISATION_PERMISSIONS` grants
 * itself — anything else (a platform bundle, a `{service}.admin` superset, a
 * machine identity, an unknown name) grants nothing.
 */
export function organisationAuthority(
\tclaims: Claims,
\talias: string,
\taliases: Record<string, string> = {},
): string[] {
\tconst groups = organisationGroups(claims, alias);
\tif (!groups) return [];
\tconst orgBundles = new Set(ORGANISATION_BUNDLES);
\tconst orgPermissions = new Set(ORGANISATION_PERMISSIONS);
\tconst out: string[] = [];
\tfor (const raw of groups) {
\t\tif (!raw) continue;
\t\tconst group = Object.prototype.hasOwnProperty.call(aliases, raw) ? aliases[raw] : raw;
\t\tif (orgBundles.has(group)) out.push(...ROLE_BUNDLES[group]);
\t\telse if (orgPermissions.has(group)) out.push(group);
\t}
\treturn orderedUnique(out);
}

/**
 * The grant set a route-level check reads: platform authority plus what each
 * organisation grants within itself. Twin of `ds_auth.Principal.authority` for a
 * user. The organisation part can never hold a superset or a platform-only
 * permission, so it never adds up to a platform grant.
 */
export function userAuthority(claims: Claims, aliases: Record<string, string> = {}): string[] {
\tconst out = [...platformAuthority(claims)];
\tfor (const alias of organisationAliases(claims)) {
\t\tout.push(...organisationAuthority(claims, alias, aliases));
\t}
\treturn orderedUnique(out);
}

/** Twin of `ds_auth.permissions.grant_satisfies`: `{service}.admin` is a superset. */
export function grantSatisfies(grant: string, required: string): boolean {
\tif (grant === required) return true;
\tif (grant.endsWith('.admin')) {
\t\tconst service = grant.slice(0, -'.admin'.length);
\t\treturn required.startsWith(`${service}.`);
\t}
\treturn false;
}

/** Twin of `ds_auth.permissions.has_permission`. */
export function hasPermission(grants: Iterable<string>, required: Iterable<string>): boolean {
\tconst held = [...grants];
\tfor (const r of required) {
\t\tif (held.some((g) => grantSatisfies(g, r))) return true;
\t}
\treturn false;
}

/**
 * Does this person hold a required permission **for one organisation**? Twin of
 * `ds_auth.Principal.grants_in`: platform authority holds everywhere; otherwise
 * only `alias`'s own groups count, and only for a member.
 */
export function grantsIn(
\tclaims: Claims,
\talias: string,
\trequired: string[],
\taliases: Record<string, string> = {},
): boolean {
\treturn hasPermission(
\t\t[...platformAuthority(claims), ...organisationAuthority(claims, alias, aliases)],
\t\trequired,
\t);
}

/** A person holding the `platform-admin` realm role. */
export function isPlatformAdmin(claims: Claims): boolean {
\treturn realmRoles(claims).includes(PLATFORM_ADMIN_ROLE);
}

/**
 * Parse and **validate** a Layer B alias map from its JSON env form — the twin
 * of `ds_auth.bundles.parse_group_aliases`. An alias may only name an
 * **organisation** bundle: never a capability, never a platform bundle (only a
 * realm role grants one). Anything else is dropped (and logged), and malformed
 * JSON yields an empty map rather than a silently different one.
 */
export function parseGroupAliases(raw: string | null | undefined): Record<string, string> {
\tif (!raw || !raw.trim()) return {};

\tlet parsed: unknown;
\ttry {
\t\tparsed = JSON.parse(raw);
\t} catch (e) {
\t\tconsole.error(`[ds-portal] group alias map is not valid JSON — no aliases applied: ${e}`);
\t\treturn {};
\t}
\tif (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
\t\tconsole.error('[ds-portal] group alias map must be a JSON object — no aliases applied.');
\t\treturn {};
\t}

\tconst orgBundles = new Set(ORGANISATION_BUNDLES);
\tconst aliases: Record<string, string> = {};
\tfor (const [foreign, target] of Object.entries(parsed as Record<string, unknown>)) {
\t\tif (typeof target !== 'string') {
\t\t\tconsole.error(`[ds-portal] ignoring non-string alias entry ${foreign} -> ${String(target)}`);
\t\t\tcontinue;
\t\t}
\t\tif (!orgBundles.has(target)) {
\t\t\tconsole.error(
\t\t\t\t`[ds-portal] ignoring alias ${foreign} -> ${target}: not an organisation role bundle. ` +
\t\t\t\t\t`An alias may only name one of ${[...ORGANISATION_BUNDLES].sort().join(', ')}.`,
\t\t\t);
\t\t\tcontinue;
\t\t}
\t\taliases[foreign] = target;
\t}
\treturn aliases;
}
"""


def write_typescript(repo_root: Path) -> Path:
    target = repo_root / PORTAL_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_typescript(), encoding="utf-8")
    return target
