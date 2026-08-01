/**
 * Access-token verification — the portal's half of the trust boundary.
 *
 * The portal sits behind oauth2-proxy and reads the human's access token from
 * `X-Auth-Request-Access-Token`. The proxy vouches for that token, but the
 * portal still mints `X-Subject-Id` + `X-User-VC` server-side from whatever the
 * token claims, so a token the portal accepts reaches the consent plane. It must
 * therefore verify the token itself, not merely decode it: an earlier version
 * base64-decoded the payload and checked only `exp`, which accepted any unsigned
 * JWT naming any email.
 *
 * This mirrors the backend reference, `ds_auth.jwt.verify_token`: resolve the
 * signing key from the realm JWKS, then require a valid signature, the expected
 * issuer, and an unexpired token. Audience is not checked here — the portal is
 * not an API and the human token's audience is the browser session, not a
 * service; every ds service the portal calls re-verifies the token with its own
 * audience expectation.
 */
import { env } from '$env/dynamic/private';
import { createRemoteJWKSet, jwtVerify, type JWTPayload, type JWTVerifyGetKey } from 'jose';

/** Clock skew tolerance, matching `ds_auth`'s default leeway. */
const LEEWAY_SECONDS = 60;

/**
 * The realm issuer every human token is minted by. **No compose-shaped
 * fallback**: an unset issuer under Helm used to default to a dev URL, which
 * silently made every signature check verify against the wrong realm (or none),
 * so VC-gated routes bounced to `/` with nothing to act on. Fail loudly instead
 * — a misconfigured deployment should refuse to authenticate, not half-work.
 */
export function resolveIssuer(): string {
	const issuer = env.KEYCLOAK_ISSUER_URL;
	if (!issuer) {
		throw new Error(
			'KEYCLOAK_ISSUER_URL is not set. The portal cannot verify access tokens ' +
				'without the realm issuer — set it to the Keycloak realm URL ' +
				'(e.g. https://keycloak.<domain>/realms/dataspaces).',
		);
	}
	return issuer.replace(/\/+$/, '');
}

/**
 * JWKS is fetched from the issuer and cached by jose (it re-fetches on an
 * unknown `kid`, so key rotation is handled). One set per issuer, memoised so a
 * new remote set is not built per request.
 */
const jwksByIssuer = new Map<string, JWTVerifyGetKey>();

function remoteJwks(issuer: string): JWTVerifyGetKey {
	let jwks = jwksByIssuer.get(issuer);
	if (!jwks) {
		jwks = createRemoteJWKSet(new URL(`${issuer}/protocol/openid-connect/certs`));
		jwksByIssuer.set(issuer, jwks);
	}
	return jwks;
}

/**
 * Verify a token against a key set and issuer, returning its claims or `null`.
 *
 * `null` on **every** failure — bad signature, wrong issuer, expired, malformed
 * — because the one caller (`hooks.server.ts`) treats "no valid token" as "no
 * session", and a thrown error there would 500 a page that should simply
 * redirect to sign-in. Split out from I/O so it is unit-testable with a local
 * key set (no network, no realm).
 */
export async function verifyToken(
	token: string,
	jwks: JWTVerifyGetKey,
	issuer: string,
): Promise<JWTPayload | null> {
	try {
		const { payload } = await jwtVerify(token, jwks, {
			issuer,
			clockTolerance: LEEWAY_SECONDS,
			requiredClaims: ['exp'],
		});
		return payload;
	} catch {
		return null;
	}
}

/**
 * Verify a token forwarded by the proxy, resolving the realm JWKS and issuer
 * from the environment. The production entry point; `verifyToken` is the pure
 * core it delegates to.
 */
export async function verifyAccessToken(token: string): Promise<JWTPayload | null> {
	const issuer = resolveIssuer();
	return verifyToken(token, remoteJwks(issuer), issuer);
}
