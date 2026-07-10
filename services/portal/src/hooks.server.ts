import { SvelteKitAuth } from '@auth/sveltekit';
import Keycloak from '@auth/sveltekit/providers/keycloak';
import { env } from '$env/dynamic/private';

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
		async jwt({ token, account }) {
			// Persist access_token and scopes from Keycloak
			if (account) {
				token.accessToken = account.access_token;
				token.idToken = account.id_token;
			}
			return token;
		},
		async session({ session, token }) {
			// Forward access token to client session (available in load functions only)
			session.accessToken = token.accessToken as string | undefined;
			return session;
		},
	},
});
