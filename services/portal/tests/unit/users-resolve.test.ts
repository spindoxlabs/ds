/**
 * `resolveUser` looks a person up with `POST /users/resolve` and a JSON body.
 *
 * The identifiers never travel in the URL: a query string is recorded by every
 * access log, proxy and trace on the path, and the identity registry withdraws
 * the `GET ?email=` form after its sunset. The answer is read as before,
 * including a 404 meaning "no mapping".
 */
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { resolveUser } from '../../src/lib/server/identity-registry';

const ISSUER = 'http://keycloak.example.test/realms/dataspaces';
const REGISTRY = 'http://identity-registry.example.test';
const EMAIL = 'person-a@example.test';
const DID = 'did:web:rec.example.org:users:ex-00001';

const ENV_KEYS = [
	'KEYCLOAK_ISSUER_URL',
	'IDENTITY_REGISTRY_URL',
	'PARTICIPANT_IDENTITY_REGISTRY_URL',
	'PORTAL_SERVICE_CLIENT_SECRET',
] as const;
const saved: Record<string, string | undefined> = {};

beforeAll(() => {
	for (const k of ENV_KEYS) saved[k] = process.env[k];
	process.env.KEYCLOAK_ISSUER_URL = ISSUER;
	process.env.IDENTITY_REGISTRY_URL = REGISTRY;
	delete process.env.PARTICIPANT_IDENTITY_REGISTRY_URL;
	process.env.PORTAL_SERVICE_CLIENT_SECRET = 'test-secret';
});

afterAll(() => {
	for (const k of ENV_KEYS) {
		if (saved[k] === undefined) delete process.env[k];
		else process.env[k] = saved[k];
	}
});

/** A fetch that issues a service token and answers the registry with `registry`. */
function stubFetch(registry: () => Response) {
	const fetchMock = vi.fn(async (input: string | URL | Request) => {
		const url = String(input);
		if (url.startsWith(ISSUER)) {
			return new Response(JSON.stringify({ access_token: 'svc-token', expires_in: 300 }));
		}
		return registry();
	});
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

function registryCall(fetchMock: ReturnType<typeof stubFetch>): [string, RequestInit] {
	const call = fetchMock.mock.calls.find(([u]) => String(u).startsWith(REGISTRY));
	expect(call).toBeDefined();
	return call as unknown as [string, RequestInit];
}

describe('resolveUser', () => {
	afterEach(() => vi.unstubAllGlobals());

	it('POSTs the identifiers as a JSON body, with none of them in the URL', async () => {
		const fetchMock = stubFetch(
			() =>
				new Response(
					JSON.stringify({
						did: DID,
						subject_id: 'ex-00001',
						roles: ['data-subject'],
						credentials: [{ role: 'data-subject', vc_jws: 'vc.jws.sig' }],
					}),
				),
		);

		const identity = await resolveUser(' Person-A@Example.test', {
			realm: 'dataspaces',
			userId: 'kc-user-a',
		});

		const [url, init] = registryCall(fetchMock);
		expect(url).toBe(`${REGISTRY}/users/resolve`);
		expect(url).not.toContain('?');
		expect(url.toLowerCase()).not.toContain('person-a');
		expect(url).not.toContain('kc-user-a');
		expect(init.method).toBe('POST');
		expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
		expect(JSON.parse(init.body as string)).toEqual({
			realm: 'dataspaces',
			user_id: 'kc-user-a',
			email: EMAIL,
		});
		expect(identity).toMatchObject({
			did: DID,
			subjectId: 'ex-00001',
			roles: ['data-subject'],
			jwsByRole: { 'data-subject': 'vc.jws.sig' },
		});
	});

	it('reads a 404 as no mapping', async () => {
		const fetchMock = stubFetch(() => new Response('{"detail":"not found"}', { status: 404 }));

		expect(await resolveUser(EMAIL, null)).toBeNull();

		const [url, init] = registryCall(fetchMock);
		expect(url).not.toContain(EMAIL);
		expect(init.method).toBe('POST');
		expect(JSON.parse(init.body as string)).toEqual({ email: EMAIL });
	});

	it('does not call the registry when there is nothing to key on', async () => {
		const fetchMock = stubFetch(() => new Response('{}', { status: 422 }));

		expect(await resolveUser('  ', null)).toBeNull();
		expect(fetchMock).not.toHaveBeenCalled();
	});
});
