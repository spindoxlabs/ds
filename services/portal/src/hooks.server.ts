/**
 * Session from oauth2-proxy, not from Auth.js.
 *
 * The portal used to be a confidential OIDC client with its own cookie, its own
 * `AUTH_SECRET`, its own callback registration and its own refresh loop. It now
 * sits behind oauth2-proxy (see `services/caddy/Caddyfile`), which owns the
 * browser session and hands the access token to every request as
 * `X-Auth-Request-Access-Token`. That removes a client registration from whoever
 * administers the realm — which matters most where that is not us — and leaves
 * one login surface for the whole deployment instead of two.
 *
 * **The header is transport, never authority.** Caddy strips any client-supplied
 * `X-Auth-Request-*` before this process sees it, the token here is used only to
 * gate the UI, and every ds service re-verifies it and re-authorises the request.
 *
 * The exported session keeps exactly the shape Auth.js produced, so every
 * `+page.server.ts` and `lib/server/auth.ts` are untouched: `locals.auth()`
 * still resolves to `{ user, accessToken, userDid, userVcRoles, … }`.
 */
import { env } from '$env/dynamic/private';
import { resolveUserByEmail } from '$lib/server/identity-registry';
import { redirect, type Handle } from '@sveltejs/kit';

/** Where the browser goes to start or end a session. Caddy routes /oauth2/* here. */
const SSO_BASE = env.OAUTH2_PROXY_BASE_URL ?? 'http://sso.dataspaces.localhost:9010';

/**
 * The identity-registry lookup is a network call, and under Auth.js it happened
 * once per login. Behind a proxy there is no login event to hang it on, so it
 * would otherwise run on every request — including every asset. Cached per email
 * with a short TTL: long enough to keep page loads cheap, short enough that a
 * freshly issued credential appears without a sign-out.
 */
const IDENTITY_TTL_MS = 60_000;
type Identity = Awaited<ReturnType<typeof resolveUserByEmail>>;
const identityCache = new Map<string, { at: number; identity: Identity }>();

async function cachedIdentity(email: string): Promise<Identity> {
	const hit = identityCache.get(email);
	const now = Date.now();
	if (hit && now - hit.at < IDENTITY_TTL_MS) return hit.identity;

	const identity = await resolveUserByEmail(email);
	// A failed lookup is cached too, briefly. Without that, a person with no
	// dataspace identity yet re-queries the registry on every navigation.
	identityCache.set(email, { at: now, identity });
	return identity;
}

function decodeClaims(token: string): Record<string, unknown> | null {
	try {
		const parts = token.split('.');
		if (parts.length !== 3) return null;
		return JSON.parse(
			Buffer.from(parts[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf-8'),
		);
	} catch {
		return null;
	}
}

function bearerFrom(request: Request): string | null {
	// oauth2-proxy sets both; the dedicated header first because `Authorization`
	// may instead carry a *service* token when a machine calls through
	// (`skip_jwt_bearer_tokens`), and that token is not a human session.
	const forwarded = request.headers.get('x-auth-request-access-token');
	if (forwarded) return forwarded;

	const authorization = request.headers.get('authorization');
	if (authorization?.toLowerCase().startsWith('bearer ')) {
		return authorization.slice(7).trim() || null;
	}
	return null;
}

async function buildSession(request: Request) {
	const accessToken = bearerFrom(request);
	if (!accessToken) return null;

	const claims = decodeClaims(accessToken);
	if (!claims) return null;

	// An expired token means the proxy's session lapsed mid-request; treat it as
	// no session so the guard redirects rather than rendering a half-authorised
	// page against a token the API will refuse.
	const exp = typeof claims.exp === 'number' ? claims.exp : 0;
	if (exp && Date.now() >= exp * 1000) return null;

	const email = String(claims.email ?? request.headers.get('x-auth-request-email') ?? '');
	const identity = email ? await cachedIdentity(email) : null;

	return {
		user: {
			name: (claims.name as string) ?? (claims.preferred_username as string) ?? email,
			email,
		},
		accessToken,
		userDid: identity?.did ?? null,
		userVcRoles: identity?.roles ?? [],
		userVcJwsByRole: identity?.jwsByRole ?? {},
		userVcRole: identity?.role ?? null,
		userVcJws: identity?.vcJws ?? null,
		userSubjectId: identity?.subjectId ?? null,
	};
}

export const handle: Handle = async ({ event, resolve }) => {
	// Sign-out is the proxy's, and the redirect chain matters: Caddy intercepts
	// /oauth2/sign_out to end the *Keycloak* session first, then Keycloak returns
	// to the proxy to drop its cookie. Clearing only one of the two leaves the
	// other able to re-authenticate silently, so "sign out" appears to do nothing.
	if (event.url.pathname === '/auth/signout') {
		throw redirect(303, `${SSO_BASE}/oauth2/sign_out`);
	}
	// `startsWith`, because the layout's form still posts to the Auth.js-shaped
	// `/auth/signin/keycloak`. Behind the proxy this path is rarely reached at all —
	// an unauthenticated browser is redirected to Keycloak before it renders a page
	// with a Sign in button — but a stale bookmark or an in-flight link should still
	// land somewhere sensible. The proxy decides where sign-in goes, not this app.
	if (event.url.pathname.startsWith('/auth/signin')) {
		const target = event.url.searchParams.get('callbackUrl') ?? '/';
		throw redirect(
			303,
			`${SSO_BASE}/oauth2/sign_in?rd=${encodeURIComponent(new URL(target, event.url.origin).toString())}`,
		);
	}

	let cached: Awaited<ReturnType<typeof buildSession>> | undefined;
	event.locals.auth = async () => {
		// Once per request: several `load` functions call this and each would
		// otherwise repeat the decode and the cache lookup.
		if (cached === undefined) cached = await buildSession(event.request);
		return cached;
	};

	return resolve(event);
};
