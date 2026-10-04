/**
 * Server-side auth utilities for SvelteKit route guards.
 *
 * Reads a person's authority from the session access token on **two levels**,
 * exactly as the backend (`libs/ds-auth`) does — because the reading itself is
 * generated from `ds_auth` (`bundles.generated.ts`), not written here:
 *
 * - **platform**: realm roles from `realm_access.roles`, and only those in the
 *   allowlist (`platform-admin` → `ds-admin`, …). No other client's
 *   `resource_access` role, and no realm-level `groups` claim, grants anything;
 * - **organisation**: each organisation's own groups, valid for that
 *   organisation only, expanded through the organisation bundles.
 *
 * This is UI gating only — the backend re-verifies and re-authorizes every
 * request against the same table.
 */
import { error, redirect } from '@sveltejs/kit';
import type { DsSession as Session } from '../../app.d.ts';
import {
	grantsIn,
	hasPermission,
	organisationAliases,
	userAuthority,
} from './bundles.generated';
import { groupAliases } from './aliases';

export interface ServerRoles {
	isAdmin: boolean;
	isDatasetAdmin: boolean;
	/** Every organisation the token names — membership, not authority. */
	organizations: string[];
	/**
	 * The organisations this person may publish for: those where
	 * `connector.provider.write` holds **within** the organisation (or
	 * platform-wide). Mirrors the connector's owner perimeter (`grants_in`).
	 */
	writableOrganizations: string[];
}

const NO_ROLES: ServerRoles = {
	isAdmin: false,
	isDatasetAdmin: false,
	organizations: [],
	writableOrganizations: [],
};

/**
 * Does the session hold `permission`?
 *
 * UI gating only — the backend re-authorizes every request. Use it to decide
 * whether to *offer* an action, so a read-only operator sees a queue without
 * buttons that would 403.
 *
 * The raw `scope` claim is deliberately **not** consulted: `ds_auth` authorises a
 * *service* on its scopes and a *user* on platform roles and organisation groups,
 * never both — a user's scope claim is OpenID plumbing, not authority.
 */
export function hasGrant(session: Session | null | undefined, ...permissions: string[]): boolean {
	if (!session?.accessToken) return false;
	const payload = decodeToken(session.accessToken);
	if (!payload) return false;
	return hasPermission(userAuthority(payload, groupAliases()), permissions);
}

/**
 * Does the session hold `permission` **for one organisation**? The twin of
 * `Principal.grants_in`, for UI that acts on an owner's resource.
 */
export function hasGrantIn(
	session: Session | null | undefined,
	alias: string,
	...permissions: string[]
): boolean {
	if (!session?.accessToken) return false;
	const payload = decodeToken(session.accessToken);
	if (!payload) return false;
	return grantsIn(payload, alias, permissions, groupAliases());
}

/**
 * Guard a route on a permission, failing with an **explanation** rather than a
 * redirect.
 *
 * A silent bounce to `/` is indistinguishable from a broken page: the operator
 * who is missing one Keycloak role or organisation group sees the app "not work" and has nothing to
 * act on. A 403 naming the permission is something they can take to whoever
 * administers the realm.
 */
export async function requireGrant(
	event: { locals: App.Locals; url: URL },
	...permissions: string[]
) {
	const session = await requireAuth(event);
	if (!hasGrant(session, ...permissions)) {
		throw error(403, {
			message:
				`This page needs the ${permissions.join(' or ')} permission, which your account ` +
				`does not currently hold. Ask an operator for the matching role or organisation group.`,
		});
	}
	return session;
}

function decodeToken(accessToken: string): Record<string, unknown> | null {
	try {
		const parts = accessToken.split('.');
		if (parts.length !== 3) return null;
		return JSON.parse(
			Buffer.from(parts[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf-8'),
		);
	} catch {
		return null;
	}
}

export function parseTokenRoles(accessToken: string | undefined): ServerRoles {
	if (!accessToken) return { ...NO_ROLES };

	try {
		const payload = decodeToken(accessToken);
		if (!payload) return { ...NO_ROLES };

		const aliases = groupAliases();
		const authority = userAuthority(payload, aliases);

		// The deployment operator: `connector.admin`, which only a platform role
		// grants (`platform-admin` → `ds-admin`). An organisation group can never
		// reach it — that is the point of the two levels.
		const isAdmin = authority.includes('connector.admin');
		const isDatasetAdmin =
			isAdmin ||
			authority.includes('connector.provider.write') ||
			authority.includes('connector.provider.read');

		const organizations = organisationAliases(payload);
		const writableOrganizations = organizations.filter((alias) =>
			grantsIn(payload, alias, ['connector.provider.write'], aliases),
		);

		return { isAdmin, isDatasetAdmin, organizations, writableOrganizations };
	} catch {
		return { ...NO_ROLES };
	}
}

export function getConsumerSubjectId(session: Session): string {
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
	if (!session?.user) {
		throw redirect(303, `/auth/signin?callbackUrl=${encodeURIComponent(event.url.pathname)}`);
	}
	return session;
}

/**
 * The grants that reach **any** page in the `/admin` section.
 *
 * The section is not one role: a full admin (`connector.admin`, and
 * `identity-registry.admin` which satisfies the `identity-registry.*` entries
 * below via the superset rule) manages everything, while an
 * `ds-onboarding-operator` holds only the organisation and agreement grants and
 * must still reach `/admin/onboarding` and `/admin/agreements`. The layout gates
 * on this union so it does not refuse the operator before each page's own
 * `requireGrant` runs; a plain member (`catalog.read`) still holds none of these
 * and is refused. `ds-participant-admin` (a provider) deliberately holds none
 * either, so the section stays operator/admin-only exactly as before.
 */
export const ADMIN_SECTION_GRANTS = [
	'connector.admin',
	'identity-registry.organizations.read',
	'identity-registry.agreements.read',
] as const;

export async function requireAdmin(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const roles = parseTokenRoles(session.accessToken);
	if (!roles.isAdmin) {
		throw error(403, {
			message:
				'Operator pages need administrator authority — the `platform-admin` realm role. ' +
				'Your account does not hold it, and no organisation group can grant it.',
		});
	}
	return { session, roles };
}

export async function requireProvider(event: { locals: App.Locals; url: URL }) {
	const session = await requireAuth(event);
	const roles = parseTokenRoles(session.accessToken);
	if (!roles.isAdmin && !roles.isDatasetAdmin) {
		throw error(403, {
			message:
				'Provider pages need `connector.provider.read` in one of your organisations. Your ' +
				'account does not hold it — ask an operator for the matching organisation group.',
		});
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

/**
 * The consumer guard for a standalone `+server.ts` endpoint.
 *
 * SvelteKit does **not** run `+layout.server.ts` for `+server.ts` handlers, so
 * `requireConsumer` on the consumer layout guards the pages but none of these
 * API routes — each must guard itself. `requireConsumer` also fails with a
 * `redirect(303,'/')`, which is wrong for a `fetch` caller: it would silently
 * follow to an HTML page. This fails with a JSON `error` the caller can read —
 * 401 when there is no session, 403 when the session is not a ConsumerUser.
 */
export async function requireConsumerApi(event: { locals: App.Locals }) {
	const session = await event.locals.auth();
	if (!session?.user) {
		throw error(401, 'Authentication required.');
	}
	const subjectId = getConsumerSubjectId(session);
	if (!subjectId || !hasVcRole(session, 'ConsumerUser')) {
		throw error(403, 'A ConsumerUser credential is required to use the consumer data plane.');
	}
	return {
		session,
		token: session.accessToken ?? '',
		subjectId,
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
