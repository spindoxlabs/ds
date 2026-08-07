/**
 * Where "sign out" actually goes — `REV-04`.
 *
 * ## The defect this replaces
 *
 * Signing out cleared the oauth2-proxy cookie and left the **Keycloak SSO
 * session** untouched, so the next visit re-authenticated silently and sign-out
 * appeared to do nothing. Two sessions exist behind this proxy and clearing
 * either one alone is not a sign-out.
 *
 * The chain that clears both was written **in the Caddyfile**, twice — once in
 * the `(auth)` snippet and once in the portal's site block. Neither ran: the
 * portal redirects to `OAUTH2_PROXY_BASE_URL`, which in dev is
 * `sso.dataspaces.localhost`, and that host's block proxies `/oauth2/*` straight
 * to oauth2-proxy without importing either. **And Kubernetes has no Caddy at
 * all** — `grep -rn 'sign_out\|end_session' helm/` returned nothing — so in the
 * cluster there was no implementation of this chain in any file, while
 * `hooks.server.ts` explained the redirect in terms of "Caddy intercepts". Code
 * that reads as correct in the one mode where nothing implements it.
 *
 * ## Why it lives here rather than in the proxy or the gateway
 *
 * This module is the only place both modes share. Caddy is the dev edge; the
 * cluster uses nginx Ingress annotations, and the chart deliberately avoids
 * configuration-snippet annotations (see `ds-portal/templates/ingress.yaml`), so
 * a redirect rule expressed in the gateway must be written twice in two
 * dialects and can drift — which is exactly what happened. Expressed here it is
 * written once and is the same URL in dev and in production.
 *
 * ## The order, which is not a free choice
 *
 * Keycloak's `end_session` **first**, returning to the proxy's `/oauth2/sign_out`
 * second, is the order the Caddyfile used and the order the realm is registered
 * for. It also fails in the safe direction: if the browser abandons the chain
 * midway the SSO session — the one that silently re-authenticates — is already
 * gone, and a surviving proxy cookie only outlives it until the access token
 * expires. The reverse order leaves the re-authenticating half alive.
 *
 * `post_logout_redirect_uri` must be registered on the client. Keycloak 18+
 * rejects an unregistered one outright, which is why the realm contract carries
 * it (`docs/deployment/keycloak.md`) and why this builds the URL from
 * `OAUTH2_PROXY_BASE_URL` — the same value the proxy serves itself on — rather
 * than from the portal's own origin.
 *
 * ## `id_token_hint`, and why the first live run needed it
 *
 * The URL above — `client_id` plus `post_logout_redirect_uri`, copied from the
 * Caddyfile — **stops at a Keycloak confirmation page**. Measured, not guessed:
 * the first live run of `tests/ui/signout.spec.ts` traced the redirect to
 * `.../protocol/openid-connect/logout?client_id=…` and went no further, with the
 * session still alive. RP-Initiated Logout lets the OP ask the user to confirm,
 * and without an `id_token_hint` Keycloak does.
 *
 * A confirmation page is not a smaller version of this bug — it *is* this bug:
 * the person clicked "Sign out", so anyone who closes the tab at that prompt is
 * left signed in, which is the outcome the whole chain exists to prevent.
 *
 * With a valid `id_token_hint` the OP knows which session to end and logs out
 * without prompting. The portal has one to give: oauth2-proxy's
 * `set_authorization_header` puts the **ID token** on `Authorization` (verified
 * on the running stack — `typ: "ID"`, `aud: oauth2_proxy`), which is a different
 * token from the access token on `X-Auth-Request-Access-Token`.
 *
 * `client_id` is sent alongside it rather than instead of it. The spec allows
 * both and makes the OP check they agree, and it keeps the fallback honest: with
 * no ID token — a machine caller, or a proxy configured without that flag — the
 * URL degrades to the confirming form rather than to a request Keycloak cannot
 * attribute to a client at all.
 */

/** The realm-relative path of Keycloak's RP-initiated logout endpoint. */
const END_SESSION_PATH = 'protocol/openid-connect/logout';

/** oauth2-proxy's own sign-out path, under its configured `proxy_prefix`. */
const PROXY_SIGN_OUT_PATH = 'oauth2/sign_out';

export interface SignOutTargets {
	/** The realm issuer, e.g. `https://keycloak.example.org/realms/dataspaces`. */
	issuer: string;
	/** Where the browser reaches oauth2-proxy — `OAUTH2_PROXY_BASE_URL`. */
	ssoBase: string;
	/**
	 * The **proxy's** Keycloak client id, not the portal's service client.
	 *
	 * Keycloak requires `client_id` (or an `id_token_hint`) alongside
	 * `post_logout_redirect_uri`, and it validates the URI against *that*
	 * client's registration. The portal never holds the id token — the proxy
	 * does — so the client id is the half of the pair we can supply.
	 */
	proxyClientId: string;
	/**
	 * The **ID token** oauth2-proxy forwards on `Authorization`, if present.
	 *
	 * Without it Keycloak shows a logout confirmation page and the session
	 * survives until someone clicks it. Optional because the header is not
	 * guaranteed — `skip_jwt_bearer_tokens` lets a machine's own bearer arrive
	 * here instead, and a proxy without `set_authorization_header` sends none.
	 */
	idToken?: string | null;
}

function join(base: string, path: string): string {
	return `${base.replace(/\/+$/, '')}/${path}`;
}

/**
 * The single hop that ends both sessions.
 *
 * Returns Keycloak's `end_session` URL, carrying the proxy's sign-out as its
 * `post_logout_redirect_uri`. Percent-encoding is `URL`'s, not hand-rolled: the
 * Caddyfile spelled this URL with a literal `%3A%2F%2F` sequence, which is a
 * second thing to get right by hand every time the host changes.
 */
export function buildSignOutUrl({
	issuer,
	ssoBase,
	proxyClientId,
	idToken,
}: SignOutTargets): string {
	const url = new URL(join(issuer, END_SESSION_PATH));
	url.searchParams.set('client_id', proxyClientId);
	url.searchParams.set('post_logout_redirect_uri', join(ssoBase, PROXY_SIGN_OUT_PATH));
	// Only when we actually have one: an empty `id_token_hint` is a malformed
	// request, which Keycloak answers with an error page rather than the
	// confirming form the absent-hint case falls back to.
	if (idToken?.trim()) url.searchParams.set('id_token_hint', idToken.trim());
	return url.toString();
}
