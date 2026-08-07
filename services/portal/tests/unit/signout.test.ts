/**
 * `REV-04` — signing out must end **both** sessions.
 *
 * The defect these pin was not a wrong URL; it was a URL written in a file
 * neither mode read. So the assertions below are about the *shape of the chain*
 * — Keycloak first, the proxy second, the proxy's own host in the return URI —
 * rather than about one literal string, which is what a test of the old
 * Caddyfile would have checked while the cluster ran no Caddy.
 */
import { describe, expect, it } from 'vitest';

import { buildSignOutUrl } from '../../src/lib/server/signout';

const DEV = {
	issuer: 'http://keycloak.dataspaces.localhost/realms/dataspaces',
	ssoBase: 'http://sso.dataspaces.localhost',
	proxyClientId: 'oauth2_proxy',
};

const CLUSTER = {
	issuer: 'https://sso.example.org/realms/dataspaces',
	// In Kubernetes there is no separate SSO host: `ds-portal`'s `_env.tpl` sets
	// `OAUTH2_PROXY_BASE_URL` to the portal origin, and the proxy serves
	// /oauth2/* on it.
	ssoBase: 'https://portal.ds.example.org',
	proxyClientId: 'oauth2_proxy',
};

describe('buildSignOutUrl', () => {
	it('sends the browser to Keycloak, not to the proxy', () => {
		// The whole defect in one assertion: the old code redirected straight to
		// the proxy's sign_out, which clears the cookie and leaves the SSO
		// session able to re-authenticate on the next request.
		const url = new URL(buildSignOutUrl(DEV));
		expect(url.origin).toBe('http://keycloak.dataspaces.localhost');
		expect(url.pathname).toBe('/realms/dataspaces/protocol/openid-connect/logout');
	});

	it('comes back through the proxy so the cookie is cleared too', () => {
		const url = new URL(buildSignOutUrl(DEV));
		expect(url.searchParams.get('post_logout_redirect_uri')).toBe(
			'http://sso.dataspaces.localhost/oauth2/sign_out',
		);
	});

	it('names the proxy client, which is what Keycloak validates the return URI against', () => {
		// Not the portal's service client. Sending `svc-ds-portal` here would make
		// Keycloak reject a `post_logout_redirect_uri` registered on the proxy.
		expect(new URL(buildSignOutUrl(DEV)).searchParams.get('client_id')).toBe('oauth2_proxy');
	});

	it('builds the same chain in the cluster, where there is no Caddy and no SSO host', () => {
		// `REV-04`'s real finding: `helm/` contained no sign-out hop at all, so
		// this case had no implementation anywhere. The portal origin doubles as
		// the proxy's host there.
		const url = new URL(buildSignOutUrl(CLUSTER));
		expect(url.origin).toBe('https://sso.example.org');
		expect(url.searchParams.get('post_logout_redirect_uri')).toBe(
			'https://portal.ds.example.org/oauth2/sign_out',
		);
	});

	it('percent-encodes the return URI', () => {
		// The Caddyfile spelled this by hand as `http%3A%2F%2F…`, once per copy.
		// `URL` does it, so a host change cannot leave one copy half-encoded.
		expect(buildSignOutUrl(DEV)).toContain(
			'post_logout_redirect_uri=http%3A%2F%2Fsso.dataspaces.localhost%2Foauth2%2Fsign_out',
		);
	});

	it('tolerates a trailing slash on either input', () => {
		// `.env` values are hand-edited and `OAUTH2_PROXY_BASE_URL` is a bare
		// origin, so a trailing slash is a plausible typo. Doubling the slash
		// would produce a URI that does not match the registered one, and
		// Keycloak's refusal reads as a realm misconfiguration.
		const url = buildSignOutUrl({
			...DEV,
			issuer: `${DEV.issuer}/`,
			ssoBase: `${DEV.ssoBase}/`,
		});
		expect(url).toBe(buildSignOutUrl(DEV));
	});

	it('sends id_token_hint when the proxy forwarded one', () => {
		// Without it Keycloak stops at a confirmation page and the session lives on
		// until someone clicks through — measured on the running stack, and the
		// reason the first live run of the journey failed against a URL every unit
		// test here already agreed with.
		const url = new URL(buildSignOutUrl({ ...DEV, idToken: 'header.payload.sig' }));
		expect(url.searchParams.get('id_token_hint')).toBe('header.payload.sig');
		// Both, not either: the spec has the OP check they agree, and client_id is
		// what validates the return URI if the hint is stale.
		expect(url.searchParams.get('client_id')).toBe('oauth2_proxy');
	});

	it('omits id_token_hint entirely rather than sending it empty', () => {
		// An empty `id_token_hint` is malformed and Keycloak answers with an error
		// page — strictly worse than the confirming form the absent case falls
		// back to. `??`-style defaulting through a template string is how that
		// would arrive here as the literal "undefined".
		for (const idToken of [undefined, null, '', '   ']) {
			const url = new URL(buildSignOutUrl({ ...DEV, idToken }));
			expect(url.searchParams.has('id_token_hint'), `idToken=${JSON.stringify(idToken)}`).toBe(
				false,
			);
		}
	});

	it('preserves a path-prefixed issuer', () => {
		// Keycloak behind a path prefix (`/auth`, the pre-17 default some
		// deployments keep) must not lose it — `new URL(path, base)` would.
		const url = new URL(
			buildSignOutUrl({ ...DEV, issuer: 'https://id.example.org/auth/realms/dataspaces' }),
		);
		expect(url.pathname).toBe('/auth/realms/dataspaces/protocol/openid-connect/logout');
	});
});
