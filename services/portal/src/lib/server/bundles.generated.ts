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


export const ROLE_BUNDLES: Record<string, string[]> = {
	'ds-admin': [
		'identity-registry.admin',
		'connector.admin',
		'provenance.read',
		'provenance.write',
		'catalog.read',
	],
	'ds-member': [
		'catalog.read',
	],
	'ds-onboarding-operator': [
		'identity-registry.organizations.read',
		'identity-registry.organizations.write',
		'identity-registry.agreements.read',
		'identity-registry.participants.write',
		'identity-registry.read',
	],
	'ds-participant-admin': [
		'connector.provider.read',
		'connector.provider.write',
		'connector.history.read',
		'connector.registry.invalidate',
		'connector.ingestion.record',
		'connector.disclosure.record',
		'catalog.read',
		'provenance.read',
		'identity-registry.read',
		'identity-registry.membership.read',
	],
	'ds-participant-viewer': [
		'connector.provider.read',
		'connector.history.read',
		'catalog.read',
		'provenance.read',
		'identity-registry.read',
	],
};

export const MACHINE_IDENTITY_PERMISSIONS: string[] = [
	'connector.internal',
	'connector.webhook',
];

export const PLATFORM_ADMIN_ROLE = 'platform-admin';

export const PLATFORM_BUNDLES: string[] = [
	'ds-admin',
	'ds-onboarding-operator',
];

export const ORGANISATION_BUNDLES: string[] = [
	'ds-member',
	'ds-participant-admin',
	'ds-participant-viewer',
];

export const REALM_ROLE_BUNDLES: Record<string, string> = {
	'ds-onboarding-operator': 'ds-onboarding-operator',
	'platform-admin': 'ds-admin',
};

export const ORGANISATION_PERMISSIONS: string[] = [
	'catalog.read',
	'connector.consent.holder.read',
	'connector.disclosure.record',
	'connector.history.read',
	'connector.ingestion.record',
	'connector.provider.read',
	'connector.provider.write',
	'connector.registry.invalidate',
	'identity-registry.membership.read',
	'identity-registry.read',
	'provenance.read',
];

type Claims = Record<string, unknown>;

function orderedUnique(values: Iterable<string>): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const v of values) {
		if (v && !seen.has(v)) {
			seen.add(v);
			out.push(v);
		}
	}
	return out;
}

/**
 * `realm_access.roles` — and nowhere else. Never `groups`, never a top-level
 * `roles`, never `resource_access.<client>.roles`. Twin of
 * `ds_auth.jwt.extract_realm_roles`.
 */
export function realmRoles(claims: Claims): string[] {
	const access = claims.realm_access;
	if (!access || typeof access !== 'object' || Array.isArray(access)) return [];
	const roles = (access as Record<string, unknown>).roles;
	if (!Array.isArray(roles)) return [];
	return orderedUnique(roles.filter((r): r is string => typeof r === 'string'));
}

/** The organisation aliases in the `organization` claim. */
export function organisationAliases(claims: Claims): string[] {
	const orgs = claims.organization;
	if (!orgs || typeof orgs !== 'object' || Array.isArray(orgs)) return [];
	return Object.entries(orgs as Record<string, unknown>)
		.filter(([, data]) => !!data && typeof data === 'object' && !Array.isArray(data))
		.map(([alias]) => alias);
}

/**
 * The groups held **within** one organisation, leading slash stripped. Twin of
 * `ds_auth.models.Organization.groups`. `null` when not a member.
 */
export function organisationGroups(claims: Claims, alias: string): string[] | null {
	const orgs = claims.organization;
	if (!orgs || typeof orgs !== 'object' || Array.isArray(orgs)) return null;
	if (!Object.prototype.hasOwnProperty.call(orgs, alias)) return null;
	const data = (orgs as Record<string, unknown>)[alias];
	if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
	const groups = (data as Record<string, unknown>).groups;
	if (!Array.isArray(groups)) return [];
	return groups
		.filter((g): g is string => typeof g === 'string' && g.trim() !== '')
		.map((g) => g.replace(/^\/+/, ''));
}

/**
 * What allowlisted realm roles grant, deployment-wide. Twin of
 * `ds_auth.bundles.platform_authority`: a role not in `REALM_ROLE_BUNDLES`
 * grants nothing, and there is no pass-through at this level.
 */
export function platformAuthority(claims: Claims): string[] {
	const out: string[] = [];
	for (const role of realmRoles(claims)) {
		const bundle = REALM_ROLE_BUNDLES[role];
		if (bundle) out.push(...ROLE_BUNDLES[bundle]);
	}
	return orderedUnique(out);
}

/**
 * What one organisation's own groups grant, within it. Twin of
 * `ds_auth.bundles.organisation_authority`: a Layer B alias first, then an
 * organisation bundle expands, then a name in `ORGANISATION_PERMISSIONS` grants
 * itself — anything else (a platform bundle, a `{service}.admin` superset, a
 * machine identity, an unknown name) grants nothing.
 */
export function organisationAuthority(
	claims: Claims,
	alias: string,
	aliases: Record<string, string> = {},
): string[] {
	const groups = organisationGroups(claims, alias);
	if (!groups) return [];
	const orgBundles = new Set(ORGANISATION_BUNDLES);
	const orgPermissions = new Set(ORGANISATION_PERMISSIONS);
	const out: string[] = [];
	for (const raw of groups) {
		if (!raw) continue;
		const group = Object.prototype.hasOwnProperty.call(aliases, raw) ? aliases[raw] : raw;
		if (orgBundles.has(group)) out.push(...ROLE_BUNDLES[group]);
		else if (orgPermissions.has(group)) out.push(group);
	}
	return orderedUnique(out);
}

/**
 * The grant set a route-level check reads: platform authority plus what each
 * organisation grants within itself. Twin of `ds_auth.Principal.authority` for a
 * user. The organisation part can never hold a superset or a platform-only
 * permission, so it never adds up to a platform grant.
 */
export function userAuthority(claims: Claims, aliases: Record<string, string> = {}): string[] {
	const out = [...platformAuthority(claims)];
	for (const alias of organisationAliases(claims)) {
		out.push(...organisationAuthority(claims, alias, aliases));
	}
	return orderedUnique(out);
}

/** Twin of `ds_auth.permissions.grant_satisfies`: `{service}.admin` is a superset. */
export function grantSatisfies(grant: string, required: string): boolean {
	if (grant === required) return true;
	if (grant.endsWith('.admin')) {
		const service = grant.slice(0, -'.admin'.length);
		return required.startsWith(`${service}.`);
	}
	return false;
}

/** Twin of `ds_auth.permissions.has_permission`. */
export function hasPermission(grants: Iterable<string>, required: Iterable<string>): boolean {
	const held = [...grants];
	for (const r of required) {
		if (held.some((g) => grantSatisfies(g, r))) return true;
	}
	return false;
}

/**
 * Does this person hold a required permission **for one organisation**? Twin of
 * `ds_auth.Principal.grants_in`: platform authority holds everywhere; otherwise
 * only `alias`'s own groups count, and only for a member.
 */
export function grantsIn(
	claims: Claims,
	alias: string,
	required: string[],
	aliases: Record<string, string> = {},
): boolean {
	return hasPermission(
		[...platformAuthority(claims), ...organisationAuthority(claims, alias, aliases)],
		required,
	);
}

/** A person holding the `platform-admin` realm role. */
export function isPlatformAdmin(claims: Claims): boolean {
	return realmRoles(claims).includes(PLATFORM_ADMIN_ROLE);
}

/**
 * Parse and **validate** a Layer B alias map from its JSON env form — the twin
 * of `ds_auth.bundles.parse_group_aliases`. An alias may only name an
 * **organisation** bundle: never a capability, never a platform bundle (only a
 * realm role grants one). Anything else is dropped (and logged), and malformed
 * JSON yields an empty map rather than a silently different one.
 */
export function parseGroupAliases(raw: string | null | undefined): Record<string, string> {
	if (!raw || !raw.trim()) return {};

	let parsed: unknown;
	try {
		parsed = JSON.parse(raw);
	} catch (e) {
		console.error(`[ds-portal] group alias map is not valid JSON — no aliases applied: ${e}`);
		return {};
	}
	if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
		console.error('[ds-portal] group alias map must be a JSON object — no aliases applied.');
		return {};
	}

	const orgBundles = new Set(ORGANISATION_BUNDLES);
	const aliases: Record<string, string> = {};
	for (const [foreign, target] of Object.entries(parsed as Record<string, unknown>)) {
		if (typeof target !== 'string') {
			console.error(`[ds-portal] ignoring non-string alias entry ${foreign} -> ${String(target)}`);
			continue;
		}
		if (!orgBundles.has(target)) {
			console.error(
				`[ds-portal] ignoring alias ${foreign} -> ${target}: not an organisation role bundle. ` +
					`An alias may only name one of ${[...ORGANISATION_BUNDLES].sort().join(', ')}.`,
			);
			continue;
		}
		aliases[foreign] = target;
	}
	return aliases;
}
