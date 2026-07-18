import { env } from '$env/dynamic/private';

function identityRegistryUrl(): string {
	return env.IDENTITY_REGISTRY_URL ?? 'http://172.17.0.1:30005';
}

let cachedToken: { token: string; expiresAt: number } | null = null;
let warnedDefaultSecret = false;

// Client id/secret come from env; the in-code defaults keep local dev working.
// Using the default secret is insecure, so warn (once) when it falls back.
const DEFAULT_SERVICE_CLIENT = 'svc-ds-portal';

async function getServiceToken(): Promise<string> {
	if (cachedToken && cachedToken.expiresAt > Date.now() + 30_000) {
		return cachedToken.token;
	}

	const issuer = env.AUTH_KEYCLOAK_ISSUER ?? 'http://keycloak:9080/realms/dataspaces';
	const tokenUrl = `${issuer}/protocol/openid-connect/token`;
	const clientId = env.PORTAL_SERVICE_CLIENT_ID ?? DEFAULT_SERVICE_CLIENT;
	const clientSecret = env.PORTAL_SERVICE_CLIENT_SECRET ?? DEFAULT_SERVICE_CLIENT;

	if (!env.PORTAL_SERVICE_CLIENT_SECRET && !warnedDefaultSecret) {
		warnedDefaultSecret = true;
		console.warn(
			`[ds-portal] PORTAL_SERVICE_CLIENT_SECRET is not set — using the insecure ` +
				`default secret for client "${clientId}". Set a real secret in production.`,
		);
	}

	try {
		const res = await fetch(tokenUrl, {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams({
				grant_type: 'client_credentials',
				client_id: clientId,
				client_secret: clientSecret,
			}),
		});
		if (!res.ok) {
			console.error(`Service token request failed: ${res.status}`);
			return '';
		}
		const data = (await res.json()) as { access_token: string; expires_in: number };
		cachedToken = { token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 };
		return cachedToken.token;
	} catch (e) {
		console.error('Failed to acquire service token:', e);
		return '';
	}
}

export interface ResolvedIdentity {
	did: string;
	role: string | null;
	vcJws: string | null;
	subjectId: string;
}

export async function resolveUserByEmail(email: string): Promise<ResolvedIdentity | null> {
	if (!email) return null;
	const serviceToken = await getServiceToken();
	if (!serviceToken) return null;

	const url = `${identityRegistryUrl()}/users/resolve?email=${encodeURIComponent(email.trim().toLowerCase())}`;
	try {
		const res = await fetch(url, {
			headers: { Authorization: `Bearer ${serviceToken}` },
		});
		if (res.status === 404) return null;
		if (!res.ok) {
			console.error(`identity-registry /users/resolve failed: ${res.status}`);
			return null;
		}
		const data = (await res.json()) as {
			did: string;
			role?: string | null;
			vc_jws?: string | null;
			subject_id: string;
		};
		return {
			did: data.did,
			role: data.role ?? null,
			vcJws: data.vc_jws ?? null,
			subjectId: data.subject_id,
		};
	} catch (e) {
		console.error('identity-registry unreachable:', e);
		return null;
	}
}
