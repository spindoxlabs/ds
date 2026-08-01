/**
 * The nav persona — which sections a signed-in user sees.
 *
 * Computed **server-side**, deliberately. It used to be derived in a client
 * store from the raw token, which had two faults the server guard did not: it
 * read the token's groups *unexpanded*, so a `ds-participant-admin` group never
 * became `connector.provider.read` and the Provider nav was hidden from users
 * `requireProvider` admits; and it applied no Layer B aliases, which the client
 * cannot (they are server env). Deriving it here, through the same
 * `parseTokenRoles` the guards use, makes the nav and the guard agree by
 * construction.
 *
 * This is display only — every route re-authorises server-side regardless.
 */
import type { DsSession as Session } from '../../app.d.ts';
import { parseTokenRoles } from './auth';

export interface UserPersona {
	isAuthenticated: boolean;
	name: string;
	email?: string;
	/** Can manage assets and approve/reject consents. */
	isProvider: boolean;
	isAdmin: boolean;
	/** Any authenticated user can be a data subject. */
	isSubject: boolean;
	organizations: string[];
}

const GUEST: UserPersona = {
	isAuthenticated: false,
	name: 'Guest',
	isProvider: false,
	isAdmin: false,
	isSubject: false,
	organizations: [],
};

export function derivePersona(session: Session | null | undefined): UserPersona {
	if (!session?.user) return GUEST;

	const name = session.user.name ?? session.user.email ?? 'User';
	const email = session.user.email ?? undefined;

	// No token on the session — authenticated, but no authority to read.
	if (!session.accessToken) {
		return { isAuthenticated: true, name, email, isProvider: false, isAdmin: false, isSubject: true, organizations: [] };
	}

	const roles = parseTokenRoles(session.accessToken);
	return {
		isAuthenticated: true,
		name,
		email,
		isProvider: roles.isAdmin || roles.isDatasetAdmin,
		isAdmin: roles.isAdmin,
		isSubject: true,
		organizations: roles.organizations,
	};
}
