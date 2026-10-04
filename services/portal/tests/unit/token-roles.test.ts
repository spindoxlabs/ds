import { describe, it, expect } from 'vitest';
import { parseTokenRoles } from '../../src/lib/server/auth';

function token(claims: Record<string, unknown>): string {
	const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
	return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64(claims)}.sig`;
}

describe('parseTokenRoles — only realm objects that exist', () => {
	it('does not treat the non-existent `admin` client role as admin', () => {
		expect(parseTokenRoles(token({ resource_access: { 'ds-portal': { roles: ['admin'] } } })).isAdmin).toBe(false);
	});

	it('treats the platform-admin realm role as admin, and nothing else', () => {
		expect(parseTokenRoles(token({ realm_access: { roles: ['platform-admin'] } })).isAdmin).toBe(true);
		// The retired names: a realm role `ds-admin`, a realm group, an org group.
		expect(parseTokenRoles(token({ realm_access: { roles: ['ds-admin'] } })).isAdmin).toBe(false);
		expect(parseTokenRoles(token({ groups: ['connector.admin', '/ds-admin'] })).isAdmin).toBe(false);
		const orgAdmin = { organization: { 'example-org': { groups: ['/ds-admin', '/connector.admin'] } } };
		expect(parseTokenRoles(token(orgAdmin)).isAdmin).toBe(false);
	});

	it('treats an organisation provider grant as a dataset admin — and not a realm one', () => {
		const org = { organization: { 'example-org': { groups: ['/ds-participant-admin'] } } };
		expect(parseTokenRoles(token(org)).isDatasetAdmin).toBe(true);
		expect(parseTokenRoles(token({ realm_access: { roles: ['dataset.admin'] } })).isDatasetAdmin).toBe(false);
		expect(parseTokenRoles(token({ groups: ['ds-participant-admin'] })).isDatasetAdmin).toBe(false);
	});

	it('a plain member is neither', () => {
		const r = parseTokenRoles(token({ organization: { 'example-org': { groups: ['/ds-member'] } } }));
		expect(r.isAdmin).toBe(false);
		expect(r.isDatasetAdmin).toBe(false);
	});

	it('names the organisations it may publish for — authority, not membership', () => {
		const r = parseTokenRoles(
			token({
				organization: {
					'example-org': { groups: ['/ds-participant-viewer'] },
					'grid-operator': { groups: ['/ds-participant-admin'] },
				},
			}),
		);
		expect(r.organizations.sort()).toEqual(['example-org', 'grid-operator']);
		expect(r.writableOrganizations).toEqual(['grid-operator']);
	});
});
