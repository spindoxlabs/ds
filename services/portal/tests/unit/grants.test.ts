import { describe, it, expect, afterEach, vi } from 'vitest';
import { hasGrant } from '../../src/lib/server/auth';

/** A syntactically valid but unsigned JWT — `hasGrant` decodes an already-verified session token. */
function tokenWith(claims: Record<string, unknown>): string {
	const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
	return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64(claims)}.sig`;
}

function session(claims: Record<string, unknown>) {
	return { accessToken: tokenWith(claims), user: { email: 'u@example.test' } };
}

describe('extractGrants (via hasGrant)', () => {
	it('does NOT grant a capability that appears only in the user scope claim', () => {
		// A user's scope is OpenID plumbing plus default client scopes — never the
		// user's authority. `connector.admin` in `scope` must not gate the UI.
		const s = session({ scope: 'openid profile email connector.admin' });
		expect(hasGrant(s, 'connector.admin')).toBe(false);
		expect(hasGrant(s, 'connector.provider.read')).toBe(false);
	});

	it('grants the expansion of a bundle group', () => {
		const s = session({ groups: ['ds-participant-admin'] });
		expect(hasGrant(s, 'connector.provider.read')).toBe(true);
		expect(hasGrant(s, 'connector.provider.write')).toBe(true);
	});

	it('honours the .admin superset rule for a realm/client role', () => {
		const s = session({ realm_access: { roles: ['connector.admin'] } });
		expect(hasGrant(s, 'connector.provider.write')).toBe(true);
	});

	it('grants an org-scoped bundle group from the organization claim', () => {
		const s = session({ organization: { 'grid-operator': { groups: ['ds-participant-viewer'] } } });
		expect(hasGrant(s, 'connector.provider.read')).toBe(true);
	});

	it('does not read organization.<alias>.roles (ds_auth never emits it)', () => {
		const s = session({ organization: { 'grid-operator': { roles: ['ds-participant-admin'] } } });
		expect(hasGrant(s, 'connector.provider.write')).toBe(false);
	});
});

describe('extractGrants with a Layer B alias map', () => {
	afterEach(() => {
		delete process.env.PORTAL_OIDC_GROUP_ALIASES;
		vi.resetModules();
	});

	it('translates a foreign group name to its ds bundle before expanding', async () => {
		process.env.PORTAL_OIDC_GROUP_ALIASES = JSON.stringify({ 'celine-manager': 'ds-participant-admin' });
		vi.resetModules();
		const { hasGrant: fresh } = await import('../../src/lib/server/auth');
		expect(fresh(session({ groups: ['celine-manager'] }), 'connector.provider.write')).toBe(true);
	});

	it('ignores an alias whose target is a capability, not a bundle', async () => {
		process.env.PORTAL_OIDC_GROUP_ALIASES = JSON.stringify({ 'celine-manager': 'connector.provider.write' });
		vi.resetModules();
		const { hasGrant: fresh } = await import('../../src/lib/server/auth');
		// The alias is dropped; the group falls through as itself and grants nothing.
		expect(fresh(session({ groups: ['celine-manager'] }), 'connector.provider.write')).toBe(false);
	});
});
