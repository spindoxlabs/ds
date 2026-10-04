/**
 * Two levels of authority — the portal's half of the parity table.
 *
 * `libs/ds-auth/tests/parity/authority-cases.json` is decided here by the
 * generated twin (`bundles.generated.ts`) and the portal's own guards, and in
 * `libs/ds-auth/tests/test_two_levels.py` by `ds_auth.Principal`. Both are held
 * to the same hand-written expectations, so the UI cannot offer what the API
 * refuses, or hide what it allows.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { hasGrant, parseTokenRoles } from '../../src/lib/server/auth';
import {
	grantsIn,
	hasPermission,
	isPlatformAdmin,
	parseGroupAliases,
	platformAuthority,
	userAuthority,
} from '../../src/lib/server/bundles.generated';

interface Case {
	name: string;
	claims: Record<string, unknown>;
	aliases: string | null;
	expect: {
		is_platform_admin: boolean;
		operator: boolean;
		platform: string[];
		authority: string[];
		grants: Record<string, boolean>;
		grants_in: { alias: string; perm: string; result: boolean }[];
	};
}

const CASES_FILE = fileURLToPath(
	new URL('../../../../libs/ds-auth/tests/parity/authority-cases.json', import.meta.url),
);
const { cases } = JSON.parse(readFileSync(CASES_FILE, 'utf-8')) as { cases: Case[] };

function token(claims: Record<string, unknown>): string {
	const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
	return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64(claims)}.sig`;
}

const sorted = (xs: string[]) => [...new Set(xs)].sort();

describe('the shared parity table', () => {
	it('covers the four cases the plan names', () => {
		const names = cases.map((c) => c.name).join(' | ');
		for (const needle of [
			'admins member is not a platform admin',
			'platform-admin realm role holds everywhere',
			'realm group still present in a token grants nothing',
			'role on an unrelated client grants nothing',
		]) {
			expect(names).toContain(needle);
		}
	});

	for (const c of cases) {
		it(c.name, () => {
			const aliases = parseGroupAliases(c.aliases);
			const e = c.expect;

			expect(isPlatformAdmin(c.claims)).toBe(e.is_platform_admin);
			expect(sorted(platformAuthority(c.claims))).toEqual(sorted(e.platform));
			expect(sorted(userAuthority(c.claims, aliases))).toEqual(sorted(e.authority));
			for (const [perm, result] of Object.entries(e.grants)) {
				expect(hasPermission(userAuthority(c.claims, aliases), [perm]), perm).toBe(result);
			}
			for (const g of e.grants_in) {
				expect(grantsIn(c.claims, g.alias, [g.perm], aliases), JSON.stringify(g)).toBe(g.result);
			}

			// Through the guards the routes actually call. The portal's alias map
			// comes from its environment (unset here), so cases that need one are
			// decided through the generated functions above only.
			const roles = parseTokenRoles(token(c.claims));
			expect(roles.isAdmin).toBe(e.operator);
			if (c.aliases === null) {
				const session = { accessToken: token(c.claims), user: { email: 'u@example.test' } };
				for (const [perm, result] of Object.entries(e.grants)) {
					expect(hasGrant(session, perm), perm).toBe(result);
				}
			}
		});
	}
});

/**
 * The same three people on tokens a real local Keycloak issued — the twin of
 * `libs/ds-auth/tests/integration/test_two_levels_real_tokens.py`. Skipped unless
 * `DS_PORTAL_IT_ISSUER` names a realm whose login client allows the password
 * grant. `DS_PORTAL_IT_PLATFORM_ADMIN` is `user:password`, `DS_PORTAL_IT_ORG_ADMIN`
 * `user:password:alias`; `DS_PORTAL_IT_LEGACY_GROUP_TOKEN` is an access token that
 * still carries a realm `groups` claim.
 */
const IT_ISSUER = process.env.DS_PORTAL_IT_ISSUER;

describe.skipIf(!IT_ISSUER)('real tokens from a local realm', () => {
	const clientId = process.env.DS_PORTAL_IT_CLIENT_ID ?? 'oauth2_proxy';
	const clientSecret = process.env.DS_PORTAL_IT_CLIENT_SECRET ?? clientId;
	const scope = process.env.DS_PORTAL_IT_SCOPE ?? 'openid email profile organization:*';
	const nowhere = 'no-such-organisation-for-this-test';

	async function passwordToken(username: string, password: string): Promise<string> {
		const res = await fetch(`${IT_ISSUER}/protocol/openid-connect/token`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
			body: new URLSearchParams({
				grant_type: 'password',
				client_id: clientId,
				client_secret: clientSecret,
				username,
				password,
				scope,
			}),
		});
		expect(res.status, `${username} could not log in`).toBe(200);
		return ((await res.json()) as { access_token: string }).access_token;
	}

	const claimsOf = (t: string) =>
		JSON.parse(Buffer.from(t.split('.')[1], 'base64url').toString('utf-8')) as Record<string, unknown>;

	it('the platform-admin role is the platform administrator', async () => {
		const [user, password] = (process.env.DS_PORTAL_IT_PLATFORM_ADMIN ?? 'admin@example.test:admin').split(':');
		const t = await passwordToken(user, password);
		const session = { accessToken: t, user: { email: user } };
		expect(isPlatformAdmin(claimsOf(t))).toBe(true);
		expect(parseTokenRoles(t).isAdmin).toBe(true);
		expect(hasGrant(session, 'identity-registry.admin')).toBe(true);
		expect(grantsIn(claimsOf(t), nowhere, ['connector.provider.write'])).toBe(true);
	});

	it('an organisation admin is not a platform admin', async () => {
		const [user, password, alias] = (
			process.env.DS_PORTAL_IT_ORG_ADMIN ?? 'gridops@example.test:gridops:grid-operator'
		).split(':');
		const t = await passwordToken(user, password);
		const roles = parseTokenRoles(t);
		expect(roles.organizations).toContain(alias);
		expect(roles.isAdmin).toBe(false);
		expect(isPlatformAdmin(claimsOf(t))).toBe(false);
		expect(platformAuthority(claimsOf(t))).toEqual([]);
		expect(hasGrant({ accessToken: t, user: { email: user } }, 'connector.admin')).toBe(false);
		expect(grantsIn(claimsOf(t), nowhere, ['connector.provider.read'])).toBe(false);
	});

	it.skipIf(!process.env.DS_PORTAL_IT_LEGACY_GROUP_TOKEN)(
		'a realm group still in a token grants nothing',
		() => {
			const t = process.env.DS_PORTAL_IT_LEGACY_GROUP_TOKEN as string;
			const claims = claimsOf(t);
			const groups = claims.groups as string[];
			expect(Array.isArray(groups) && groups.length > 0).toBe(true);
			const { groups: _dropped, ...without } = claims;
			expect(sorted(userAuthority(claims))).toEqual(sorted(userAuthority(without)));
			expect(parseTokenRoles(t).isAdmin).toBe(false);
			for (const g of groups) {
				expect(hasPermission(userAuthority(claims), [g.replace(/^\/+/, '')])).toBe(false);
			}
		},
	);
});
