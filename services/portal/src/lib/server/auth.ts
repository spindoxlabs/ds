/**
 * Server-side auth utilities for SvelteKit route guards.
 * Parses Keycloak JWT claims from the session access token.
 */
import { redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

export interface ServerRoles {
	isAdmin: boolean;
	isDatasetAdmin: boolean;
	canQuery: boolean;
}

export function parseTokenRoles(accessToken: string | undefined): ServerRoles {
	if (!accessToken) return { isAdmin: false, isDatasetAdmin: false, canQuery: false };

	try {
		const parts = accessToken.split('.');
		if (parts.length !== 3) return { isAdmin: false, isDatasetAdmin: false, canQuery: false };
		const payload: Record<string, unknown> = JSON.parse(
			Buffer.from(parts[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf-8')
		);
		const clientId = env.KEYCLOAK_CLIENT_ID ?? 'ds-portal';
		const portalRoles: string[] =
			(payload?.resource_access as Record<string, { roles?: string[] }>)?.[clientId]?.roles ?? [];
		const realmRoles: string[] =
			(payload?.realm_access as { roles?: string[] })?.roles ?? [];
		const scopes = ((payload?.scope as string) ?? '').split(' ');

		return {
			isAdmin: portalRoles.includes('admin') || realmRoles.includes('ds-admin'),
			isDatasetAdmin:
				portalRoles.includes('dataset.admin') || realmRoles.includes('dataset.admin'),
			canQuery: scopes.includes('dataspaces.query') || scopes.includes('dataset.query'),
		};
	} catch {
		return { isAdmin: false, isDatasetAdmin: false, canQuery: false };
	}
}

/**
 * Require authentication. Redirect to sign-in if not authenticated.
 * Returns the session (non-null guaranteed).
 */
export async function requireAuth(event: { locals: App.Locals; url: URL }) {
	const session = await event.locals.auth();
	if (!session?.user) {
		throw redirect(303, `/auth/signin?callbackUrl=${encodeURIComponent(event.url.pathname)}`);
	}
	return session;
}

/**
 * Require admin role. Redirect to home if authenticated but not admin.
 */
export async function requireAdmin(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const roles = parseTokenRoles(session.accessToken);
	if (!roles.isAdmin) {
		throw redirect(303, '/');
	}
	return { session, roles };
}

/**
 * Require dataset.admin or admin role (provider access).
 */
export async function requireProvider(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const roles = parseTokenRoles(session.accessToken);
	if (!roles.isAdmin && !roles.isDatasetAdmin) {
		throw redirect(303, '/');
	}
	return { session, roles };
}
