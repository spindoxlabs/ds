/**
 * Server-side auth utilities for SvelteKit route guards.
 *
 * Parses Keycloak authority from the session access token. Authority is
 * dual-sourced, matching the backend (libs/ds-auth): a user may carry it as
 * Keycloak roles (realm or client) AND/OR as groups whose names mirror the
 * backend permission vocabulary (e.g. `connector.admin`,
 * `connector.provider.write`). This is UI gating only — the backend re-verifies
 * and re-authorizes every request.
 */
import { redirect } from '@sveltejs/kit';
import type { Session } from '@auth/core/types';

export interface ServerRoles {
	isAdmin: boolean;
	isDatasetAdmin: boolean;
	canQuery: boolean;
	organizations: string[];
}

/**
 * All Keycloak roles: realm roles plus every client's roles under
 * `resource_access` (so authority is not tied to one client id — "dual role").
 */
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

/**
 * Merge Keycloak groups from realm-level `groups` and org-level
 * `organization.<alias>.groups` (legacy) or `organization.<alias>.roles`
 * (KC 26+ native organizations). Mirrors `ds_auth.extract_groups`.
 */
function extractGroups(payload: Record<string, unknown>): string[] {
	const out: string[] = [];
	const realm = payload.groups;
	if (Array.isArray(realm)) out.push(...realm.filter((g): g is string => typeof g === 'string'));
	const orgs = payload.organization;
	if (orgs && typeof orgs === 'object') {
		for (const org of Object.values(orgs as Record<string, unknown>)) {
			if (!org || typeof org !== 'object') continue;
			const o = org as Record<string, unknown>;
			for (const key of ['groups', 'roles']) {
				const entries = o[key];
				if (Array.isArray(entries)) out.push(...entries.filter((x): x is string => typeof x === 'string'));
			}
		}
	}
	return out.map((g) => g.replace(/^\/+/, ''));
}

/**
 * Extract the set of KC organization aliases the user belongs to from the
 * `organization` JWT claim. Works with both legacy (celine-policies) and
 * KC 26+ native organization claim structures.
 */
function extractOrganizations(payload: Record<string, unknown>): string[] {
	const orgs = payload.organization;
	if (!orgs || typeof orgs !== 'object') return [];
	return Object.keys(orgs as Record<string, unknown>);
}

export function parseTokenRoles(accessToken: string | undefined): ServerRoles {
	if (!accessToken) return { isAdmin: false, isDatasetAdmin: false, canQuery: false, organizations: [] };

	try {
		const parts = accessToken.split('.');
		if (parts.length !== 3) return { isAdmin: false, isDatasetAdmin: false, canQuery: false, organizations: [] };
		const payload: Record<string, unknown> = JSON.parse(
			Buffer.from(parts[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf-8')
		);

		// Dual-sourced authority: roles (realm + any client) AND groups.
		const authorities = new Set<string>([...extractRoles(payload), ...extractGroups(payload)]);
		const scopes = ((payload?.scope as string) ?? '').split(' ');

		const isAdmin =
			authorities.has('ds-admin') || // realm role
			authorities.has('admin') || // ds-portal client role
			authorities.has('connector.admin'); // group (backend permission)
		const isDatasetAdmin =
			isAdmin ||
			authorities.has('dataset.admin') ||
			authorities.has('connector.provider.write') ||
			authorities.has('connector.provider.read');
		const canQuery =
			scopes.includes('dataspaces.query') ||
			scopes.includes('dataset.query') ||
			authorities.has('dataset.query');

		const organizations = extractOrganizations(payload);

		return { isAdmin, isDatasetAdmin, canQuery, organizations };
	} catch {
		return { isAdmin: false, isDatasetAdmin: false, canQuery: false, organizations: [] };
	}
}

export function getConsumerSubjectId(session: Session): string {
	if (session.userDid && session.userVcJws) return session.userDid;
	return session.userDid ?? '';
}

/**
 * Does the user hold this VC role?
 *
 * A person legitimately holds several — the same human is a data subject about
 * their own consumption and a consumer user acting for an organisation — so this
 * asks "includes", never "equals". `userVcRole` is consulted as a fallback for
 * sessions minted before `userVcRoles` existed.
 */
export function hasVcRole(session: Session | null | undefined, role: string): boolean {
	if (!session) return false;
	if (session.userVcRoles?.length) return session.userVcRoles.includes(role);
	return session.userVcRole === role;
}

/**
 * The VC to present for a call that requires `role`.
 *
 * Falls back to the newest credential so a session minted before per-role
 * selection existed still works; returns null when there is nothing to present,
 * which the connector answers with a 401 rather than a silent success.
 */
export function vcJwsForRole(
	session: Session | null | undefined,
	role: string,
): string | null {
	if (!session) return null;
	return session.userVcJwsByRole?.[role] ?? session.userVcJws ?? null;
}

export async function requireAuth(event: { locals: App.Locals; url: URL }) {
	const session = await event.locals.auth();
	if (!session?.user || session.error === 'RefreshTokenError') {
		throw redirect(303, `/auth/signin?callbackUrl=${encodeURIComponent(event.url.pathname)}`);
	}
	return session;
}

export async function requireAdmin(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const roles = parseTokenRoles(session.accessToken);
	if (!roles.isAdmin) {
		throw redirect(303, '/');
	}
	return { session, roles };
}

export async function requireProvider(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const roles = parseTokenRoles(session.accessToken);
	if (!roles.isAdmin && !roles.isDatasetAdmin) {
		throw redirect(303, '/');
	}
	return { session, roles };
}

/**
 * Consumer routes need a `ConsumerUser` credential, because every call they make
 * presents one.
 *
 * There is deliberately **no admin bypass**. There used to be one, and it was
 * dead code: an admin has no identity-registry mapping, so `subjectId` is empty
 * and the guard rejected them at the first condition anyway. Worse, letting an
 * admin through would only defer the failure to the connector, which requires a
 * VC these routes cannot produce. An operator who must act as a consumer needs a
 * credential issued, not a UI exception.
 */
export async function requireConsumer(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const roles = parseTokenRoles(session.accessToken);
	const subjectId = getConsumerSubjectId(session);
	if (!subjectId || !hasVcRole(session, 'ConsumerUser')) {
		throw redirect(303, '/');
	}
	return {
		session,
		roles,
		subjectId,
		userVcRole: 'ConsumerUser',
		vcJws: vcJwsForRole(session, 'ConsumerUser'),
	};
}

export async function requireDataSubject(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const subjectId = session.userDid ?? '';
	if (!subjectId || !hasVcRole(session, 'DataSubject')) {
		throw redirect(303, '/');
	}
	return {
		session,
		subjectId,
		userVcRole: 'DataSubject',
		vcJws: vcJwsForRole(session, 'DataSubject'),
	};
}
