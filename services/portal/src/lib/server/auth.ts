/**
 * Server-side auth utilities for SvelteKit route guards.
 * Parses Keycloak JWT claims from the session access token.
 */
import { redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import type { Session } from '@auth/core/types';

export interface ServerRoles {
	isAdmin: boolean;
	isDatasetAdmin: boolean;
	canQuery: boolean;
}

function demoAdminUsers(): string[] {
	return (env.PORTAL_DEMO_ADMIN_USERS ?? 'admin')
		.split(',')
		.map((item) => item.trim())
		.filter(Boolean);
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
		const username = String(
			payload.preferred_username ?? payload.name ?? payload.email ?? payload.sub ?? '',
		);
		const isDemoAdmin = demoAdminUsers().includes(username);

		return {
			isAdmin: portalRoles.includes('admin') || realmRoles.includes('ds-admin') || isDemoAdmin,
			isDatasetAdmin:
				portalRoles.includes('dataset.admin') || realmRoles.includes('dataset.admin') || isDemoAdmin,
			canQuery: scopes.includes('dataspaces.query') || scopes.includes('dataset.query'),
		};
	} catch {
		return { isAdmin: false, isDatasetAdmin: false, canQuery: false };
	}
}

export function getConsumerSubjectId(session: Session): string {
	if (session.userDid && session.userVcJws) return session.userDid;
	if (parseTokenRoles(session.accessToken).isAdmin) return env.PORTAL_DEMO_CONSUMER_SUBJECT_ID ?? 'test';
	return session.userDid ?? '';
}

export async function requireAuth(event: { locals: App.Locals; url: URL }) {
	const session = await event.locals.auth();
	if (!session?.user) {
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

export async function requireConsumer(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const roles = parseTokenRoles(session.accessToken);
	const subjectId = getConsumerSubjectId(session);
	const userVcRole = session.userVcRole ?? null;
	if (!subjectId || (!roles.isAdmin && userVcRole !== 'ConsumerUser')) {
		throw redirect(303, '/');
	}
	return { session, roles, subjectId, userVcRole };
}

export async function requireDataSubject(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const subjectId = session.userDid ?? '';
	const userVcRole = session.userVcRole ?? null;
	if (!subjectId || userVcRole !== 'DataSubject') {
		throw redirect(303, '/');
	}
	return { session, subjectId, userVcRole };
}
