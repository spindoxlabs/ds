"""Emit the role-bundle table as TypeScript for the portal.

The portal gates its UI on the same permissions the API enforces, so it needs the
same expansion. Hand-writing a second copy of a *table* is worse than the
duplicated *matcher* that already exists: a matcher is one rule that can be
eyeballed, whereas a table drifts entry by entry and every drift is a page that
either hides an action the user may take or offers one the API will refuse.

So the Python table is the definition and the TypeScript is generated from it,
with a no-diff test (`tests/test_bundles_export.py`) making the checked-in copy a
build artifact rather than a document someone remembers to update.

Regenerate with ``task -d libs/ds-auth bundles:generate``.
"""
from __future__ import annotations

from pathlib import Path

from .bundles import MACHINE_IDENTITY_PERMISSIONS, ROLE_BUNDLES

# Relative to the repository root.
PORTAL_TARGET = Path("services/portal/src/lib/server/bundles.generated.ts")

_HEADER = """\
// GENERATED FILE — DO NOT EDIT.
//
// Source: libs/ds-auth/src/ds_auth/bundles.py
// Regenerate: task -d libs/ds-auth bundles:generate
//
// The role bundles a user token's groups are expanded through, mirroring
// `ds_auth.bundles` exactly. The portal gates its UI on the result; the backend
// re-authorizes every request against the same table, so a stale copy here shows
// the wrong buttons rather than granting anything.
"""


def _ts_string_array(values: tuple[str, ...] | list[str], indent: str) -> str:
    body = "".join(f"{indent}\t'{v}',\n" for v in values)
    return f"[\n{body}{indent}]"


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

    lines.append(
        """\
/**
 * Expand role bundles into capabilities — the TypeScript twin of
 * `ds_auth.bundles.expand_bundles`. Three rules, in order: a known bundle
 * expands; a machine-identity permission is dropped (never grantable to a
 * human, however the group is named); anything else passes through verbatim, so
 * a realm still carrying the old scope-named groups keeps working.
 */
export function expandBundles(groups: Iterable<string>): string[] {
\tconst seen = new Set<string>();
\tconst result: string[] = [];
\tconst machine = new Set(MACHINE_IDENTITY_PERMISSIONS);

\tconst add = (permission: string) => {
\t\tif (permission && !seen.has(permission)) {
\t\t\tseen.add(permission);
\t\t\tresult.push(permission);
\t\t}
\t};

\tfor (const group of groups) {
\t\tif (typeof group !== 'string' || !group) continue;
\t\tconst capabilities = ROLE_BUNDLES[group];
\t\tif (capabilities) {
\t\t\tfor (const capability of capabilities) add(capability);
\t\t} else if (machine.has(group)) {
\t\t\tcontinue;
\t\t} else {
\t\t\tadd(group);
\t\t}
\t}

\treturn result;
}
"""
    )

    return "\n".join(lines)


def write_typescript(repo_root: Path) -> Path:
    target = repo_root / PORTAL_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_typescript(), encoding="utf-8")
    return target
