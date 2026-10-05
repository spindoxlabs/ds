/**
 * What a session may show the browser, and what it must not.
 *
 * `locals.auth()` carries the person's access token and every user credential
 * they hold, because the server routes present them upstream. None of it is
 * display data. A `load` that returned the session used to ship all of it into
 * the page and into `__data.json` (`R17`). Two layers keep it server-side:
 *
 * 1. no `load` returns the session; layouts return {@link displaySession} and
 *    the fields they derive;
 * 2. the credential fields are **non-enumerable** on the session object, so a
 *    `load` that returns the session anyway serialises without them — SvelteKit
 *    (devalue) and `JSON.stringify` both read own enumerable keys only. Reading
 *    `session.accessToken` on the server is unchanged.
 */
import type { DsSession } from '../../app.d.ts';

/** The session fields that are credentials, never display data. */
export const CREDENTIAL_FIELDS = ['accessToken', 'userVcJws', 'userVcJwsByRole'] as const;

type Credentials = Pick<DsSession, (typeof CREDENTIAL_FIELDS)[number]>;

/** Attach the credentials to a session as non-enumerable properties. */
export function withCredentials<T extends object>(session: T, credentials: Credentials): T & Credentials {
	for (const field of CREDENTIAL_FIELDS) {
		Object.defineProperty(session, field, {
			value: credentials[field],
			enumerable: false,
			writable: false,
			configurable: false,
		});
	}
	return session as T & Credentials;
}

/** What the browser may know about who is signed in. */
export interface DisplaySession {
	user: { name: string | null; email: string | null };
}

export function displaySession(session: DsSession | null | undefined): DisplaySession | null {
	if (!session?.user) return null;
	return { user: { name: session.user.name ?? null, email: session.user.email ?? null } };
}

/**
 * Response headers set on every response (`hooks.server.ts`).
 *
 * The Content-Security-Policy is SvelteKit's (`kit.csp` in `svelte.config.js`),
 * because only the framework knows the hashes of the inline scripts it renders.
 * `X-Frame-Options` repeats `frame-ancestors 'none'` for clients that ignore CSP.
 */
export const SECURITY_HEADERS: Readonly<Record<string, string>> = {
	'X-Content-Type-Options': 'nosniff',
	'Referrer-Policy': 'no-referrer',
	'X-Frame-Options': 'DENY',
};
