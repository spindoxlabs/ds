import { describe, it, expect } from 'vitest';
import { requireConsumerApi } from '../../src/lib/server/auth';

type Session = Record<string, unknown> | null;

function event(session: Session) {
	return { locals: { auth: async () => session } as App.Locals };
}

async function status(fn: () => Promise<unknown>): Promise<number> {
	try {
		await fn();
		return 200;
	} catch (e) {
		return (e as { status?: number }).status ?? -1;
	}
}

const consumerSession = {
	user: { email: 'c@example.test' },
	accessToken: 'tok',
	userDid: 'did:web:users.dataspaces.localhost:consumer',
	userVcRoles: ['ConsumerUser'],
	userVcJwsByRole: { ConsumerUser: 'jws-consumer' },
	userVcJws: 'jws-consumer',
};

describe('requireConsumerApi', () => {
	it('401s an unauthenticated caller (the endpoints ran open before)', async () => {
		expect(await status(() => requireConsumerApi(event(null)))).toBe(401);
	});

	it('403s a session that is not a ConsumerUser', async () => {
		const s = { user: { email: 'x@example.test' }, accessToken: 'tok', userDid: 'did:web:x', userVcRoles: ['DataSubject'] };
		expect(await status(() => requireConsumerApi(event(s)))).toBe(403);
	});

	it('403s a ConsumerUser with no subject id', async () => {
		const s = { user: { email: 'x@example.test' }, accessToken: 'tok', userDid: '', userVcRoles: ['ConsumerUser'] };
		expect(await status(() => requireConsumerApi(event(s)))).toBe(403);
	});

	it('passes a ConsumerUser and returns its credential material', async () => {
		const out = await requireConsumerApi(event(consumerSession));
		expect(out.subjectId).toBe(consumerSession.userDid);
		expect(out.vcJws).toBe('jws-consumer');
		expect(out.token).toBe('tok');
	});
});
