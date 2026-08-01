import { describe, it, expect } from 'vitest';
import { derivePersona } from '../../src/lib/server/persona';

function tokenWith(claims: Record<string, unknown>): string {
	const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
	return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64(claims)}.sig`;
}

function session(claims: Record<string, unknown>) {
	return { accessToken: tokenWith(claims), user: { name: 'Pat', email: 'pat@example.test' } };
}

describe('derivePersona', () => {
	it('shows the Provider persona for a bundle group the guard admits', () => {
		// The defect: the client store read groups unexpanded, so this group never
		// became connector.provider.read and the Provider nav was hidden.
		const p = derivePersona(session({ groups: ['ds-participant-admin'] }));
		expect(p.isProvider).toBe(true);
	});

	it('shows Admin (and thus provider) for connector.admin', () => {
		const p = derivePersona(session({ realm_access: { roles: ['connector.admin'] } }));
		expect(p.isAdmin).toBe(true);
		expect(p.isProvider).toBe(true);
	});

	it('does not admit a provider from organization.<alias>.roles', () => {
		const p = derivePersona(session({ organization: { 'grid-operator': { roles: ['ds-participant-admin'] } } }));
		expect(p.isProvider).toBe(false);
	});

	it('is a guest with no session', () => {
		expect(derivePersona(null).isAuthenticated).toBe(false);
		expect(derivePersona(undefined).isAuthenticated).toBe(false);
	});

	it('carries the org aliases through', () => {
		const p = derivePersona(session({ groups: ['ds-member'], organization: { 'grid-operator': {} } }));
		expect(p.organizations).toContain('grid-operator');
	});
});
