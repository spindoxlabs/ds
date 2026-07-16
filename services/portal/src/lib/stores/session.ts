/**
 * Client-side session store — persona detection from Keycloak roles, groups,
 * and scopes. UI display only; the server re-verifies and re-authorizes.
 * Populated by the root +layout.svelte from server-loaded session data.
 */

export interface UserPersona {
	isAuthenticated: boolean;
	name: string;
	email?: string;
	isProvider: boolean;    // has dataset.admin role in ds-portal client
	isConsumer: boolean;    // has dataspaces.query scope
	isAdmin: boolean;       // has admin role in ds-portal client
	isSubject: boolean;     // any authenticated user can be a data subject
}

/**
 * Parse role and scope claims from a Keycloak access token JWT.
 *
 * Token structure (Keycloak):
 *   resource_access["ds-portal"].roles → ["admin", "dataset.admin"]
 *   scope → "openid profile email dataspaces.query"
 *
 * The token is decoded client-side (not verified — the server already validated
 * it via the Auth.js callback). Only the payload claims are read.
 */
function parseJwtPayload(token: string): Record<string, unknown> {
	try {
		const parts = token.split('.');
		if (parts.length !== 3) return {};
		const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
		return JSON.parse(atob(payload));
	} catch {
		return {};
	}
}

/** All Keycloak roles: realm roles + every client's roles under resource_access. */
function extractRoles(payload: Record<string, unknown>): string[] {
	const roles: string[] = [];
	const realm = (payload.realm_access as { roles?: string[] } | undefined)?.roles;
	if (Array.isArray(realm)) roles.push(...realm);
	const resource = payload.resource_access as Record<string, { roles?: string[] }> | undefined;
	if (resource && typeof resource === 'object') {
		for (const client of Object.values(resource)) {
			if (Array.isArray(client?.roles)) roles.push(...client.roles);
		}
	}
	return roles;
}

/** Merge realm-level `groups` and org-level `organization.<alias>.groups`. */
function extractGroups(payload: Record<string, unknown>): string[] {
	const out: string[] = [];
	const realm = payload.groups;
	if (Array.isArray(realm)) out.push(...realm.filter((g): g is string => typeof g === 'string'));
	const orgs = payload.organization;
	if (orgs && typeof orgs === 'object') {
		for (const org of Object.values(orgs as Record<string, unknown>)) {
			const g = (org as { groups?: unknown })?.groups;
			if (Array.isArray(g)) out.push(...g.filter((x): x is string => typeof x === 'string'));
		}
	}
	return out.map((g) => g.replace(/^\/+/, ''));
}

export function derivePersona(
	session: { user?: { name?: string | null; email?: string | null }; accessToken?: string } | null
): UserPersona {
	if (!session?.user) {
		return {
			isAuthenticated: false,
			name: 'Guest',
			isProvider: false,
			isConsumer: false,
			isAdmin: false,
			isSubject: false,
		};
	}

	const name = session.user.name ?? session.user.email ?? 'User';
	const email = session.user.email ?? undefined;

	// No access token available — fall back to base authenticated persona
	if (!session.accessToken) {
		return {
			isAuthenticated: true,
			name,
			email,
			isProvider: false,
			isConsumer: true, // authenticated users can query by default
			isAdmin: false,
			isSubject: true,
		};
	}

	const payload = parseJwtPayload(session.accessToken);

	// Dual-sourced authority: roles (realm + any client) AND groups, mirroring
	// the server guard (src/lib/server/auth.ts) and the backend (ds-auth).
	const authorities = new Set<string>([...extractRoles(payload), ...extractGroups(payload)]);
	const scopes = ((payload?.scope as string) ?? '').split(' ');

	const isAdmin =
		authorities.has('ds-admin') || authorities.has('admin') || authorities.has('connector.admin');
	const isDatasetAdmin =
		isAdmin ||
		authorities.has('dataset.admin') ||
		authorities.has('connector.provider.write') ||
		authorities.has('connector.provider.read');
	const canQuery =
		scopes.includes('dataspaces.query') ||
		scopes.includes('dataset.query') ||
		authorities.has('dataset.query');

	return {
		isAuthenticated: true,
		name,
		email,
		// Provider: can manage assets and approve/reject consents
		isProvider: isAdmin || isDatasetAdmin,
		// Consumer: can run queries and negotiate contracts
		isConsumer: isAdmin || canQuery,
		isAdmin,
		isSubject: true,
	};
}
