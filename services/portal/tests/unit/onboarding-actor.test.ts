/**
 * The onboarding console records who acted by the operator's Keycloak user id
 * (the token `sub`), never by their email or display name, and refuses to act
 * for a session that carries no id.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const registry = vi.hoisted(() => ({
	decideApplication: vi.fn(async (..._args: unknown[]) => ({})),
	recordAgreementAcceptance: vi.fn(async (..._args: unknown[]) => ({})),
}));
vi.mock('$lib/server/identity-registry', () => registry);

import { actions } from '../../src/routes/admin/onboarding/+page.server';
import { displaySession } from '../../src/lib/server/session';

const OPERATOR_ID = '00000000-0000-4000-8000-000000000001';

function token(claims: Record<string, unknown>): string {
	const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
	return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64(claims)}.sig`;
}

function event(user: Record<string, unknown>, form: Record<string, string>) {
	const body = new FormData();
	for (const [k, v] of Object.entries(form)) body.set(k, v);
	const session = {
		user,
		accessToken: token({ sub: user.id, realm_access: { roles: ['platform-admin'] } }),
	};
	return {
		locals: { auth: async () => session },
		url: new URL('http://portal.example.test/admin/onboarding?status=pending'),
		request: new Request('http://portal.example.test/admin/onboarding', { method: 'POST', body }),
	} as never;
}

async function run(action: keyof typeof actions, ev: never): Promise<unknown> {
	try {
		return await (actions[action] as (e: never) => Promise<unknown>)(ev);
	} catch (thrown) {
		return thrown; // a redirect is thrown
	}
}

const DECIDE = { id: 'app-1', status: 'verified' };
const ACCEPT = { alias: 'example-rec', agreement: 'participation@1.0' };
const PERSON = { name: 'Example Operator', email: 'operator@example.test' };

describe('onboarding actor', () => {
	beforeEach(() => {
		registry.decideApplication.mockClear();
		registry.recordAgreementAcceptance.mockClear();
	});

	it('records a decision as the operator’s user id, not their email', async () => {
		await run('decide', event({ id: OPERATOR_ID, ...PERSON }, DECIDE));
		expect(registry.decideApplication).toHaveBeenCalledOnce();
		const body = registry.decideApplication.mock.calls[0][2] as Record<string, unknown>;
		expect(body.verified_by).toBe(OPERATOR_ID);
	});

	it('records an acceptance as the operator’s user id, not their email', async () => {
		await run('acceptAgreement', event({ id: OPERATOR_ID, ...PERSON }, ACCEPT));
		expect(registry.recordAgreementAcceptance).toHaveBeenCalledOnce();
		const body = registry.recordAgreementAcceptance.mock.calls[0][2] as Record<string, unknown>;
		expect(body.accepted_by).toBe(OPERATOR_ID);
	});

	it('refuses a decision when the session carries no user id', async () => {
		const result = (await run('decide', event({ ...PERSON }, DECIDE))) as { status?: number };
		expect(result.status).toBe(403);
		expect(registry.decideApplication).not.toHaveBeenCalled();
	});

	it('refuses an acceptance when the session carries no user id', async () => {
		const result = (await run('acceptAgreement', event({ ...PERSON }, ACCEPT))) as {
			status?: number;
		};
		expect(result.status).toBe(403);
		expect(registry.recordAgreementAcceptance).not.toHaveBeenCalled();
	});

	it('keeps the user id on the server: the display session carries name and email only', () => {
		const shown = displaySession({ user: { id: OPERATOR_ID, ...PERSON } });
		expect(JSON.stringify(shown)).not.toContain(OPERATOR_ID);
	});
});
