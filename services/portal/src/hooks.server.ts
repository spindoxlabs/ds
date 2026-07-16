import { SvelteKitAuth } from '@auth/sveltekit';
import Keycloak from '@auth/sveltekit/providers/keycloak';
import { env } from '$env/dynamic/private';
import { resolveUserByEmail } from '$lib/server/identity-registry';

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

export const { handle, signIn, signOut } = SvelteKitAuth({
	providers: [
		Keycloak({
			clientId: env.AUTH_KEYCLOAK_ID ?? 'ds-portal',
			clientSecret: env.AUTH_KEYCLOAK_SECRET ?? '',
			issuer: env.AUTH_KEYCLOAK_ISSUER ?? 'http://keycloak:8080/realms/dataspaces',
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
				token.idToken = account.id_token;

				const email = (profile?.email ?? token.email ?? '') as string;
				const identity = await resolveUserByEmail(email);
				token.userDid = identity?.did ?? null;
				token.userVcRole = identity?.role ?? null;
				token.userVcJws = identity?.vcJws ?? null;
				token.userSubjectId = identity?.subjectId ?? null;
			}
			return token;
		},
		async session({ session, token }) {
			session.accessToken = token.accessToken as string | undefined;
			session.userDid = (token.userDid as string) ?? null;
			session.userVcRole = (token.userVcRole as string) ?? null;
			session.userVcJws = (token.userVcJws as string) ?? null;
			session.userSubjectId = (token.userSubjectId as string) ?? null;
			return session;
		},
	},
});
