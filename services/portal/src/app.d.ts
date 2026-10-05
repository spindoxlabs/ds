/**
 * The session shape, owned here rather than by Auth.js.
 *
 * The portal is no longer an OIDC client: oauth2-proxy holds the browser session
 * and `hooks.server.ts` builds this object per request from the access token it
 * forwards. The shape is deliberately unchanged from what Auth.js produced, so
 * every route's `locals.auth()` call site kept working across the switch.
 */
export interface DsSession {
	/**
	 * `id` is the Keycloak user id (the token `sub`): the stable key that records
	 * who acted. Server-side only — `displaySession` sends the browser the name
	 * and email alone.
	 */
	user?: { id?: string | null; name?: string | null; email?: string | null };
	/** Non-enumerable, as are the two credential fields below (`R17`). */
	accessToken?: string;
	userDid?: string | null;
	/**
	 * Every VC role the user holds. A person legitimately holds more than one
	 * — the same human is a data subject about their own consumption and a
	 * consumer user acting for an organisation — so role checks must ask
	 * "does this include", never "does this equal".
	 */
	userVcRoles?: string[];
	/** VC-JWS per role, so a call presents the credential it actually needs. */
	userVcJwsByRole?: Record<string, string>;
	/** The newest credential. Convenience only — prefer selecting by role. */
	userVcRole?: string | null;
	userVcJws?: string | null;
	userSubjectId?: string | null;
}

declare global {
	namespace App {
		interface Locals {
			/** Resolved once per request by `hooks.server.ts`; null when unauthenticated. */
			auth(): Promise<DsSession | null>;
		}

		// No `session` in `PageData`: the session carries the person's token and
		// credentials, and page data reaches the browser (`lib/server/session.ts`).
	}
}

export {};
