/**
 * R3 — the portal resolves a person by their Keycloak login, and forwards it.
 *
 * Person routes on the connector and provenance bind the person's login token
 * to the credential's subject through the identity registry's Keycloak mapping,
 * keyed on the realm and the user id (`sub`). The portal must resolve the
 * person's DID by the **same** key: resolving by email alone can name a DID the
 * login is not bound to (a re-created account, a recycled address), and every
 * person route would then refuse them.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { realmOf, resolveBody } from '../../src/lib/server/identity-registry';
import { queryMyEvents } from '../../src/lib/server/provenance';

describe('realmOf', () => {
	it.each([
		['https://keycloak.example/realms/dataspaces', 'dataspaces'],
		['http://keycloak.dataspaces.localhost/realms/dataspaces/', 'dataspaces'],
		['https://sso.example/auth/realms/host', 'host'],
		['https://keycloak.example/', null],
		['', null],
	])('%s → %s', (issuer, realm) => {
		expect(realmOf(issuer)).toBe(realm);
	});
});

describe('resolveBody', () => {
	it('asks by the Keycloak user id, with the email only as a fallback', () => {
		expect(
			resolveBody('Subject@Example.test ', { realm: 'dataspaces', userId: 'u-1' }),
		).toEqual({ realm: 'dataspaces', user_id: 'u-1', email: 'subject@example.test' });
	});

	it('falls back to the email when there is no login to key on', () => {
		expect(resolveBody('subject@example.test', null)).toEqual({
			email: 'subject@example.test',
		});
	});
});

describe('queryMyEvents', () => {
	afterEach(() => vi.unstubAllGlobals());

	it("forwards the person's own login token beside the credential", async () => {
		const fetchMock = vi.fn(async () => new Response(JSON.stringify({ '@graph': [] })));
		vi.stubGlobal('fetch', fetchMock);

		await queryMyEvents({ limit: 10 }, 'person-token', 'did:web:x:users:s', 'vc.jws.sig');

		const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		const headers = init.headers as Record<string, string>;
		expect(headers.Authorization).toBe('Bearer person-token');
		expect(headers['X-User-VC']).toBe('vc.jws.sig');
		expect(headers['X-Subject-Id']).toBe('did:web:x:users:s');
	});
});
