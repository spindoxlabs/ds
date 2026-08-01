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

	it('still treats ds-admin and connector.admin as admin', () => {
		expect(parseTokenRoles(token({ realm_access: { roles: ['ds-admin'] } })).isAdmin).toBe(true);
		expect(parseTokenRoles(token({ groups: ['connector.admin'] })).isAdmin).toBe(true);
	});

	it('treats a real dataset.admin / provider grant as a dataset admin', () => {
		expect(parseTokenRoles(token({ groups: ['dataset.admin'] })).isDatasetAdmin).toBe(true);
		expect(parseTokenRoles(token({ groups: ['ds-participant-admin'] })).isDatasetAdmin).toBe(true);
	});

	it('a plain member is neither', () => {
		const r = parseTokenRoles(token({ groups: ['ds-member'] }));
		expect(r.isAdmin).toBe(false);
		expect(r.isDatasetAdmin).toBe(false);
	});
});
