/**
 * Client-side session store — persona detection from Keycloak JWT scopes.
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

const KEYCLOAK_CLIENT_ID =
	typeof window !== 'undefined'
		? (window.__ENV?.PUBLIC_KEYCLOAK_CLIENT_ID ?? 'ds-portal')
		: 'ds-portal';
const DEMO_ADMIN_USERS = ['admin'];

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
		const isDemoAdmin = DEMO_ADMIN_USERS.includes(name);
		return {
			isAuthenticated: true,
			name,
			email,
			isProvider: isDemoAdmin,
			isConsumer: true,   // authenticated users can query by default
			isAdmin: isDemoAdmin,
			isSubject: true,
		};
	}

	const payload = parseJwtPayload(session.accessToken);

	// Keycloak resource_access roles for the ds-portal client
	const portalRoles: string[] =
		(payload?.resource_access as Record<string, { roles?: string[] }>)?.[
			KEYCLOAK_CLIENT_ID
		]?.roles ?? [];

	// Realm-level roles (fallback for simpler Keycloak configurations)
	const realmRoles: string[] =
		(payload?.realm_access as { roles?: string[] })?.roles ?? [];

	// OAuth2 scope string
	const scopes = ((payload?.scope as string) ?? '').split(' ');
	const username = String(
		payload.preferred_username ?? payload.name ?? payload.email ?? payload.sub ?? name,
	);
	const isDemoAdminUser = DEMO_ADMIN_USERS.includes(username);

	const isAdmin = portalRoles.includes('admin') || realmRoles.includes('ds-admin') || isDemoAdminUser;
	const isDatasetAdmin =
		portalRoles.includes('dataset.admin') || realmRoles.includes('dataset.admin') || isDemoAdminUser;
	const canQuery = scopes.includes('dataspaces.query') || scopes.includes('dataset.query');

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
