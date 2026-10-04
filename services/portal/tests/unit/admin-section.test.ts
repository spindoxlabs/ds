import { describe, it, expect } from 'vitest';
import { hasGrant, ADMIN_SECTION_GRANTS } from '../../src/lib/server/auth';

function tokenWith(claims: Record<string, unknown>): string {
	const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
	return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64(claims)}.sig`;
}

const session = (claims: Record<string, unknown>) => ({
	accessToken: tokenWith(claims),
	user: { email: 'u@example.test' },
});
const admits = (claims: Record<string, unknown>) => hasGrant(session(claims), ...ADMIN_SECTION_GRANTS);
const roles = (...r: string[]) => ({ realm_access: { roles: r } });
const inOrg = (...g: string[]) => ({ organization: { 'example-org': { groups: g.map((x) => `/${x}`) } } });

describe('/admin section membership', () => {
	it('admits an onboarding operator — the seat the layout used to lock out', () => {
		expect(admits(roles('ds-onboarding-operator'))).toBe(true);
	});

	it('admits the platform administrator', () => {
		expect(admits(roles('platform-admin'))).toBe(true);
	});

	it('refuses a plain member', () => {
		expect(admits(inOrg('ds-member'))).toBe(false);
	});

	it('refuses a provider (ds-participant-admin holds no admin-section grant)', () => {
		expect(admits(inOrg('ds-participant-admin'))).toBe(false);
	});

	it('refuses the platform seats when they arrive as an organisation group or a realm group', () => {
		expect(admits(inOrg('ds-admin', 'ds-onboarding-operator'))).toBe(false);
		expect(admits({ groups: ['ds-admin', 'ds-onboarding-operator'] })).toBe(false);
	});
});
