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
import { realmOf, resolveUser, type KeycloakLogin } from '$lib/server/identity-registry';
import { buildPortalGuard } from '$lib/server/production';
import { SECURITY_HEADERS, withCredentials } from '$lib/server/session';
import { buildSignOutUrl } from '$lib/server/signout';
import { resolveIssuer, verifyAccessToken } from '$lib/server/token';
import { redirect, type Handle } from '@sveltejs/kit';

// `AUTH-04`. Module scope, so this runs once when the server starts and a
// production portal with a dev-default service secret never reaches the first
// request — the same contract every Python service's lifespan has. In dev
// (`DS_ENV=dev`, which compose sets) it logs and continues.
buildPortalGuard().enforce();

/** Where the browser goes to start or end a session. Caddy routes /oauth2/* here. */
const SSO_BASE = env.OAUTH2_PROXY_BASE_URL ?? 'http://sso.dataspaces.localhost';

/**
 * The **proxy's** Keycloak client, which is not the portal's service client.
 *
 * Only sign-out needs it: Keycloak validates `post_logout_redirect_uri` against
 * the client named in the request. The dev default matches the realm import and
 * the chart's `auth.clientId`; a deployment that renames the client sets this,
 * and `ds-portal`'s `_env.tpl` passes it from the same value the proxy release
 * uses so the two cannot drift silently.
 */
const PROXY_CLIENT_ID = env.OAUTH2_PROXY_CLIENT_ID ?? 'oauth2_proxy';

/**
 * The identity-registry lookup is a network call, and under Auth.js it happened
 * once per login. Behind a proxy there is no login event to hang it on, so it
 * would otherwise run on every request — including every asset. Cached per email
 * with a short TTL: long enough to keep page loads cheap, short enough that a
 * freshly issued credential appears without a sign-out.
 */
const IDENTITY_TTL_MS = 60_000;
type Identity = Awaited<ReturnType<typeof resolveUser>>;
const identityCache = new Map<string, { at: number; identity: Identity }>();

async function cachedIdentity(email: string, login: KeycloakLogin | null): Promise<Identity> {
	// Keyed on the login when there is one: two sessions with the same address
	// and different Keycloak users are two people (a re-created account).
	const key = login ? `${login.realm}|${login.userId}` : `email|${email}`;
	const hit = identityCache.get(key);
	const now = Date.now();
	if (hit && now - hit.at < IDENTITY_TTL_MS) return hit.identity;

	const identity = await resolveUser(email, login);
	// A failed lookup is cached too, briefly. Without that, a person with no
	// dataspace identity yet re-queries the registry on every navigation.
	identityCache.set(key, { at: now, identity });
	return identity;
}

/**
 * The ID token, which is a different token from the one `bearerFrom` returns.
 *
 * `set_authorization_header` puts the **ID token** on `Authorization` while
 * `pass_access_token` puts the *access* token on `X-Auth-Request-Access-Token`.
 * Only sign-out wants this one, as `id_token_hint` — see `lib/server/signout.ts`
 * for what Keycloak does without it. Never used to authorise anything: the two
 * are not interchangeable, and this one is not re-verified here.
 */
function idTokenFrom(request: Request): string | null {
	const authorization = request.headers.get('authorization');
	if (!authorization?.toLowerCase().startsWith('bearer ')) return null;
	return authorization.slice(7).trim() || null;
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

	// Verify the signature, issuer and expiry — never trust the payload on a bare
	// decode. A token that fails any check is treated as no session, so the guard
	// redirects to sign-in rather than building an authorised session (and minting
	// `X-Subject-Id` / `X-User-VC`) from a token the API would refuse. Expiry is
	// covered here too: a lapsed proxy session must not render a half-authorised
	// page.
	const claims = await verifyAccessToken(accessToken);
	if (!claims) return null;

	const email = String(claims.email ?? request.headers.get('x-auth-request-email') ?? '');
	const realm = realmOf(String(claims.iss ?? ''));
	const login = realm && claims.sub ? { realm, userId: String(claims.sub) } : null;
	const identity = email || login ? await cachedIdentity(email, login) : null;

	// The token and the credentials are non-enumerable: server code reads them
	// as before, and a `load` that returns this object serialises without them
	// (`lib/server/session.ts`, `R17`).
	return withCredentials(
		{
			user: {
				name: (claims.name as string) ?? (claims.preferred_username as string) ?? email,
				email,
			},
			userDid: identity?.did ?? null,
			userVcRoles: identity?.roles ?? [],
			userVcRole: identity?.role ?? null,
			userSubjectId: identity?.subjectId ?? null,
		},
		{
			accessToken,
			userVcJws: identity?.vcJws ?? null,
			userVcJwsByRole: identity?.jwsByRole ?? {},
		},
	);
}

export const handle: Handle = async ({ event, resolve }) => {
	// Two sessions exist behind this proxy — Keycloak's SSO session and the
	// proxy's cookie — and clearing either one alone is not a sign-out: the
	// survivor re-authenticates silently and sign-out appears to do nothing.
	// `buildSignOutUrl` sends the browser through both, in the order that fails
	// safe. This used to redirect to the proxy alone and rely on the gateway to
	// insert the Keycloak hop, which no gateway on either path actually did
	// (`REV-04` — see `lib/server/signout.ts` for what was wrong where).
	if (event.url.pathname === '/auth/signout') {
		throw redirect(
			303,
			buildSignOutUrl({
				issuer: resolveIssuer(),
				ssoBase: SSO_BASE,
				proxyClientId: PROXY_CLIENT_ID,
				idToken: idTokenFrom(event.request),
			}),
		);
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

	const response = await resolve(event);
	// The CSP itself is `kit.csp` (`svelte.config.js`); these are the headers
	// SvelteKit does not set.
	for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
		try {
			response.headers.set(name, value);
		} catch {
			// A `fetch` response passed through as is has immutable headers.
		}
	}
	return response;
};
