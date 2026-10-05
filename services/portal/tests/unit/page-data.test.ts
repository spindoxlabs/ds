/**
 * R17 — page data carries display data, never the person's token or credentials.
 *
 * Whatever a `load` returns is rendered into the page and served as
 * `__data.json`, which SvelteKit serialises with devalue. The session holds the
 * person's access token and every user credential they hold; the server routes
 * present them upstream and the browser needs none of them.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { stringify } from 'devalue';
import { describe, expect, it } from 'vitest';
import type { DsSession } from '../../src/app.d.ts';
import { load as rootLayout } from '../../src/routes/+layout.server';
import { load as adminLayout } from '../../src/routes/admin/+layout.server';
import { load as consentLayout } from '../../src/routes/consent/+layout.server';
import { load as consumerLayout } from '../../src/routes/consumer/+layout.server';
import { load as providerLayout } from '../../src/routes/provider/+layout.server';
import { CREDENTIAL_FIELDS, SECURITY_HEADERS, withCredentials } from '../../src/lib/server/session';
import config from '../../svelte.config.js';

function token(claims: Record<string, unknown>): string {
	const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
	return `${b64({ alg: 'RS256', typ: 'JWT' })}.${b64(claims)}.sig`;
}

// A session that reaches every section: platform admin, provider, consumer and
// subject at once. Each credential carries a marker the assertions look for.
const ACCESS_TOKEN = token({
	sub: 'marker-access-token',
	realm_access: { roles: ['platform-admin'] },
	organization: { 'example-org': { groups: ['/ds-participant-admin'] } },
});
const VC_CONSUMER = 'marker-vc-consumer';
const VC_SUBJECT = 'marker-vc-subject';
const MARKERS = [ACCESS_TOKEN, 'marker-access-token', VC_CONSUMER, VC_SUBJECT];

const DISPLAY = {
	user: { name: 'Example Person', email: 'person@example.test' },
	userDid: 'did:web:rec.example.org:users:ex-00001',
	userVcRoles: ['ConsumerUser', 'DataSubject'],
	userVcRole: 'DataSubject',
	userSubjectId: 'ex-00001',
};
const CREDENTIALS = {
	accessToken: ACCESS_TOKEN,
	userVcJws: VC_SUBJECT,
	userVcJwsByRole: { ConsumerUser: VC_CONSUMER, DataSubject: VC_SUBJECT },
};

/** The session `hooks.server.ts` builds. */
function session(): DsSession {
	return withCredentials({ ...DISPLAY }, CREDENTIALS);
}

/** A session with every field enumerable, so a layout is tested on its own. */
function plainSession(): DsSession {
	return { ...DISPLAY, ...CREDENTIALS };
}

function event(build: () => DsSession = session) {
	const s = build();
	return {
		locals: { auth: async () => s } as App.Locals,
		url: new URL('http://portal.example.test/'),
	} as never;
}

function expectNoCredential(data: unknown) {
	// Both serialisations: devalue is what `__data.json` and the inline page data
	// use, JSON is what a careless `json(data)` would use.
	for (const text of [stringify(data), JSON.stringify(data)]) {
		for (const marker of MARKERS) expect(text).not.toContain(marker);
	}
}

describe('the session object', () => {
	it('keeps its credentials readable on the server', () => {
		const s = session();
		expect(s.accessToken).toBe(ACCESS_TOKEN);
		expect(s.userVcJwsByRole?.ConsumerUser).toBe(VC_CONSUMER);
		expect(s.userVcJws).toBe(VC_SUBJECT);
	});

	it('serialises without them, should a load return it', () => {
		expectNoCredential({ session: session() });
		expect(Object.keys(session())).not.toEqual(expect.arrayContaining([...CREDENTIAL_FIELDS]));
	});

	it('does not carry them into a copy', () => {
		expectNoCredential({ ...session() });
	});
});

describe('layout data', () => {
	it.each([
		['root', rootLayout],
		['admin', adminLayout],
		['consent', consentLayout],
		['consumer', consumerLayout],
		['provider', providerLayout],
	])('%s returns no token and no credential', async (_name, load) => {
		for (const build of [session, plainSession]) {
			const data = await (load as (e: never) => Promise<unknown>)(event(build));
			expectNoCredential(data);
		}
	});

	it('the root layout still names who is signed in', async () => {
		const data = (await rootLayout(event(plainSession))) as Record<string, unknown>;
		expect(data.session).toEqual({ user: { name: 'Example Person', email: 'person@example.test' } });
		expect(data.subjectId).toBe('did:web:rec.example.org:users:ex-00001');
		expect(data.userVcRoles).toEqual(['ConsumerUser', 'DataSubject']);
	});
});

// The sweep: no `load` hands the session itself to the page. The layer above
// keeps the credentials out even then; this keeps the rest of the session out.
const ROUTES = join(__dirname, '../../src/routes');

function serverLoads(dir: string): string[] {
	return readdirSync(dir).flatMap((name) => {
		const path = join(dir, name);
		if (statSync(path).isDirectory()) return serverLoads(path);
		return /^\+(page|layout)\.server\.ts$/.test(name) ? [path] : [];
	});
}

describe('every server load', () => {
	it('returns no session, token or credential field', () => {
		const offenders = serverLoads(ROUTES).flatMap((path) => {
			const source = readFileSync(path, 'utf-8');
			const returns = source.match(/return\s*\{[^;]*?\}\s*;/gs) ?? [];
			return returns
				.filter((r) =>
					/[{,\s](session|accessToken|token|vcJws|userVcJws|userVcJwsByRole)\s*[,}]/.test(r),
				)
				.map(() => relative(ROUTES, path));
		});
		expect(offenders).toEqual([]);
	});
});

describe('response headers', () => {
	it('sets a CSP that denies framing and plugins', () => {
		const csp = config.kit?.csp;
		expect(csp?.mode).toBe('auto');
		const directives = csp?.directives ?? {};
		expect(directives['default-src']).toEqual(['self']);
		expect(directives['frame-ancestors']).toEqual(['none']);
		expect(directives['object-src']).toEqual(['none']);
		expect(directives['base-uri']).toEqual(['self']);
		expect(directives['script-src']).not.toContain('unsafe-inline');
	});

	it('sets nosniff, a referrer policy and no framing', () => {
		expect(SECURITY_HEADERS['X-Content-Type-Options']).toBe('nosniff');
		expect(SECURITY_HEADERS['Referrer-Policy']).toBe('no-referrer');
		expect(SECURITY_HEADERS['X-Frame-Options']).toBe('DENY');
	});
});
