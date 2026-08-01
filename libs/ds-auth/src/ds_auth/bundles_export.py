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
 * `ds_auth.bundles.expand_bundles`. Four rules, in order: a Layer B alias is
 * translated first (a foreign IdP's group name becomes the ds bundle a
 * deployment mapped it to); a known bundle expands; a machine-identity
 * permission is dropped (never grantable to a human, however the group is
 * named); anything else passes through verbatim, so a realm still carrying the
 * old scope-named groups keeps working.
 */
export function expandBundles(
\tgroups: Iterable<string>,
\taliases: Record<string, string> = {},
): string[] {
\tconst seen = new Set<string>();
\tconst result: string[] = [];
\tconst machine = new Set(MACHINE_IDENTITY_PERMISSIONS);

\tconst add = (permission: string) => {
\t\tif (permission && !seen.has(permission)) {
\t\t\tseen.add(permission);
\t\t\tresult.push(permission);
\t\t}
\t};

\tfor (const raw of groups) {
\t\tif (typeof raw !== 'string' || !raw) continue;
\t\t// Rule 0: translate a foreign name before anything else looks at it.
\t\tconst group = aliases[raw] ?? raw;
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

/**
 * Parse and **validate** a Layer B alias map from its JSON env form — the twin
 * of `ds_auth.bundles.parse_group_aliases`. Aliases may only name bundles, never
 * capabilities, so deployment configuration cannot become a permission table:
 * an entry whose target is not a known bundle is dropped (and warned), and
 * malformed JSON yields an empty map rather than a silently different one.
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

\tconst aliases: Record<string, string> = {};
\tfor (const [foreign, target] of Object.entries(parsed as Record<string, unknown>)) {
\t\tif (typeof target !== 'string') {
\t\t\tconsole.error(`[ds-portal] ignoring non-string alias entry ${foreign} -> ${String(target)}`);
\t\t\tcontinue;
\t\t}
\t\tif (!(target in ROLE_BUNDLES)) {
\t\t\tconsole.error(
\t\t\t\t`[ds-portal] ignoring alias ${foreign} -> ${target}: not a role bundle. ` +
\t\t\t\t\t`An alias may only name a bundle (${Object.keys(ROLE_BUNDLES).sort().join(', ')}).`,
\t\t\t);
\t\t\tcontinue;
\t\t}
\t\taliases[foreign] = target;
\t}
\treturn aliases;
}
"""
    )

    return "\n".join(lines)


def write_typescript(repo_root: Path) -> Path:
    target = repo_root / PORTAL_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_typescript(), encoding="utf-8")
    return target
