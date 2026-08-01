import { describe, it, expect } from 'vitest';
import { hasGrant, ADMIN_SECTION_GRANTS } from '../../src/lib/server/auth';

function tokenWith(claims: Record<string, unknown>): string {
	const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
	return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64(claims)}.sig`;
}

const session = (groups: string[]) => ({ accessToken: tokenWith({ groups }), user: { email: 'u@example.test' } });
const admits = (groups: string[]) => hasGrant(session(groups), ...ADMIN_SECTION_GRANTS);

describe('/admin section membership', () => {
	it('admits an onboarding operator — the seat the layout used to lock out', () => {
		expect(admits(['ds-onboarding-operator'])).toBe(true);
	});

	it('admits a full admin', () => {
		expect(admits(['ds-admin'])).toBe(true);
	});

	it('refuses a plain member', () => {
		expect(admits(['ds-member'])).toBe(false);
	});

	it('refuses a provider (ds-participant-admin holds no admin-section grant)', () => {
		expect(admits(['ds-participant-admin'])).toBe(false);
	});
});
