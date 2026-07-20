import { SvelteKitAuth } from '@auth/sveltekit';
import Keycloak from '@auth/sveltekit/providers/keycloak';
import { env } from '$env/dynamic/private';
import { resolveUserByEmail } from '$lib/server/identity-registry';
import { redirect, type Handle } from '@sveltejs/kit';
import { sequence } from '@sveltejs/kit/hooks';
import { decode } from '@auth/core/jwt';
import type { JWT } from '@auth/core/jwt';

if (!env.AUTH_SECRET) {
	console.warn(
		'[ds-portal] AUTH_SECRET is not set — using the insecure default session ' +
			'secret. Set a strong AUTH_SECRET in production.',
	);
}
if (!env.AUTH_KEYCLOAK_SECRET) {
	console.warn(
		'[ds-portal] AUTH_KEYCLOAK_SECRET is not set for the login client ' +
			`"${env.AUTH_KEYCLOAK_ID ?? 'ds-portal'}".`,
	);
}

async function refreshAccessToken(token: JWT): Promise<JWT> {
	const issuer = env.AUTH_KEYCLOAK_ISSUER ?? 'http://keycloak:9080/realms/dataspaces';
	const tokenUrl = `${issuer}/protocol/openid-connect/token`;
	try {
		const res = await fetch(tokenUrl, {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams({
				grant_type: 'refresh_token',
				client_id: env.AUTH_KEYCLOAK_ID ?? 'ds-portal',
				client_secret: env.AUTH_KEYCLOAK_SECRET ?? '',
				refresh_token: token.refreshToken as string,
			}),
		});
		if (!res.ok) {
			const body = await res.text().catch(() => '');
			console.error(`[ds-portal] Token refresh failed: ${res.status}`, body);
			return { ...token, error: 'RefreshTokenError' };
		}
		const data = await res.json();
		return {
			...token,
			accessToken: data.access_token,
			refreshToken: data.refresh_token ?? token.refreshToken,
			idToken: data.id_token ?? token.idToken,
			accessTokenExpires: Date.now() + data.expires_in * 1000,
			error: undefined,
		};
	} catch (e) {
		console.error('[ds-portal] Token refresh error:', e);
		return { ...token, error: 'RefreshTokenError' };
	}
}

const { handle: authHandle, signIn, signOut } = SvelteKitAuth({
	providers: [
		Keycloak({
			clientId: env.AUTH_KEYCLOAK_ID ?? 'ds-portal',
			clientSecret: env.AUTH_KEYCLOAK_SECRET ?? '',
			issuer: env.AUTH_KEYCLOAK_ISSUER ?? 'http://keycloak:9080/realms/dataspaces',
			authorization: {
				params: {
					scope: env.AUTH_KEYCLOAK_SCOPE ?? 'openid profile email',
				},
			},
		}),
	],
	secret: env.AUTH_SECRET ?? 'dev-secret-change-in-prod',
	trustHost: true,
	callbacks: {
		async jwt({ token, account, profile }) {
			if (account) {
				token.accessToken = account.access_token;
				token.refreshToken = account.refresh_token;
				token.accessTokenExpires = account.expires_at
					? account.expires_at * 1000
					: Date.now() + 300_000;
				token.idToken = account.id_token;
				token.error = undefined;

				const email = (profile?.email ?? token.email ?? '') as string;
				const identity = await resolveUserByEmail(email);
				token.userDid = identity?.did ?? null;
				token.userVcRole = identity?.role ?? null;
				token.userVcJws = identity?.vcJws ?? null;
				token.userSubjectId = identity?.subjectId ?? null;
			} else if (token.error === 'RefreshTokenError') {
				return token;
			} else if (
				typeof token.accessTokenExpires === 'number' &&
				Date.now() > token.accessTokenExpires - 60_000
			) {
				token = await refreshAccessToken(token);
			}
			return token;
		},
		async session({ session, token }) {
			if (token.error === 'RefreshTokenError') {
				session.error = 'RefreshTokenError';
			}
			session.accessToken = token.accessToken as string | undefined;
			session.userDid = (token.userDid as string) ?? null;
			session.userVcRole = (token.userVcRole as string) ?? null;
			session.userVcJws = (token.userVcJws as string) ?? null;
			session.userSubjectId = (token.userSubjectId as string) ?? null;
			return session;
		},
	},
});

function readSessionCookie(event: Parameters<Handle>[0]['event']) {
	const secure = event.cookies.get('__Secure-authjs.session-token');
	if (secure) return { token: secure, salt: '__Secure-authjs.session-token' as const };
	const plain = event.cookies.get('authjs.session-token');
	if (plain) return { token: plain, salt: 'authjs.session-token' as const };

	// Auth.js chunks large JWTs into .0, .1, .2, … cookies
	const prefix = event.cookies.get('__Secure-authjs.session-token.0')
		? '__Secure-authjs.session-token'
		: 'authjs.session-token';
	const chunks: string[] = [];
	for (let i = 0; ; i++) {
		const c = event.cookies.get(`${prefix}.${i}`);
		if (!c) break;
		chunks.push(c);
	}
	if (chunks.length)
		return { token: chunks.join(''), salt: prefix as 'authjs.session-token' | '__Secure-authjs.session-token' };
	return null;
}

function clearAuthCookies(event: Parameters<Handle>[0]['event']) {
	for (const base of [
		'authjs.session-token', '__Secure-authjs.session-token',
		'authjs.callback-url', '__Secure-authjs.callback-url',
		'authjs.csrf-token', '__Secure-authjs.csrf-token',
	]) {
		event.cookies.delete(base, { path: '/' });
		for (let i = 0; ; i++) {
			if (event.cookies.get(`${base}.${i}`) === undefined) break;
			event.cookies.delete(`${base}.${i}`, { path: '/' });
		}
	}
}

const keycloakSignout: Handle = async ({ event, resolve }) => {
	if (event.url.pathname === '/auth/signout' && event.request.method === 'POST') {
		const issuer = env.AUTH_KEYCLOAK_ISSUER ?? 'http://keycloak:9080/realms/dataspaces';
		const secret = env.AUTH_SECRET ?? 'dev-secret-change-in-prod';

		let idToken: string | undefined;
		const session = readSessionCookie(event);
		if (session) {
			try {
				const decoded = await decode({ token: session.token, secret, salt: session.salt });
				idToken = decoded?.idToken as string | undefined;
			} catch {
				// proceed without id_token_hint
			}
		}

		clearAuthCookies(event);

		const logoutUrl = new URL(`${issuer}/protocol/openid-connect/logout`);
		logoutUrl.searchParams.set('client_id', env.AUTH_KEYCLOAK_ID ?? 'ds-portal');
		if (idToken) {
			logoutUrl.searchParams.set('id_token_hint', idToken);
		}
		logoutUrl.searchParams.set(
			'post_logout_redirect_uri',
			`${event.url.origin}/`,
		);

		throw redirect(303, logoutUrl.toString());
	}

	return resolve(event);
};

export { signIn, signOut };
export const handle = sequence(keycloakSignout, authHandle);
