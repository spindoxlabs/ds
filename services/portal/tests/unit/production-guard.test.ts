/**
 * AUTH-04 · the portal's production guard.
 *
 * The portal was the one component still opting itself out of the platform-wide
 * `DS_ENV=production` default: `PORTAL_SERVICE_CLIENT_SECRET` fell back to the
 * client id behind a single `console.warn`. These tests are paired — the
 * configuration that must pass, and the configuration that must now refuse to
 * boot — because a guard that only proves the happy path is the warning again
 * with more steps.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ENV_KEYS = [
	'DS_ENV',
	'PORTAL_SERVICE_CLIENT_ID',
	'PORTAL_SERVICE_CLIENT_SECRET',
	'KEYCLOAK_ISSUER_URL',
] as const;

let saved: Record<string, string | undefined>;

beforeEach(() => {
	saved = Object.fromEntries(ENV_KEYS.map((k) => [k, process.env[k]]));
	vi.resetModules();
});

afterEach(() => {
	for (const [k, v] of Object.entries(saved)) {
		if (v === undefined) delete process.env[k];
		else process.env[k] = v;
	}
	vi.restoreAllMocks();
});

function setEnv(values: Record<string, string | undefined>) {
	for (const k of ENV_KEYS) delete process.env[k];
	for (const [k, v] of Object.entries(values)) {
		if (v !== undefined) process.env[k] = v;
	}
}

/** Re-import after mutating env: the module reads it when the guard is built. */
async function load() {
	return await import('$lib/server/production');
}

describe('DS_ENV', () => {
	it('defaults to production, so forgetting it is the safe direction', async () => {
		setEnv({});
		const { currentEnv, isProduction } = await load();
		expect(currentEnv()).toBe('production');
		expect(isProduction()).toBe(true);
	});

	it('matches ds_auth.current_env: dev has to be asked for', async () => {
		setEnv({ DS_ENV: 'dev' });
		const { isProduction } = await load();
		expect(isProduction()).toBe(false);
	});
});

describe('the portal guard', () => {
	const GOOD = {
		DS_ENV: 'production',
		PORTAL_SERVICE_CLIENT_ID: 'svc-ds-portal',
		PORTAL_SERVICE_CLIENT_SECRET: 'b3b1f0c2e4d5a7',
		KEYCLOAK_ISSUER_URL: 'https://sso.example.org/realms/dataspaces',
	};

	it('passes a properly configured production portal', async () => {
		setEnv(GOOD);
		const { buildPortalGuard } = await load();
		expect(() => buildPortalGuard().enforce()).not.toThrow();
	});

	it('refuses to boot when the service secret is unset', async () => {
		setEnv({ ...GOOD, PORTAL_SERVICE_CLIENT_SECRET: undefined });
		const { buildPortalGuard } = await load();
		expect(() => buildPortalGuard().enforce()).toThrow(/PORTAL_SERVICE_CLIENT_SECRET/);
	});

	it('refuses the shipped dev default', async () => {
		setEnv({ ...GOOD, PORTAL_SERVICE_CLIENT_SECRET: 'svc-ds-portal' });
		const { buildPortalGuard } = await load();
		expect(() => buildPortalGuard().enforce()).toThrow(/development default/);
	});

	it('refuses a secret equal to a renamed client id', async () => {
		// What `forbidDefault` alone cannot see, and the shape KC-01 records: a
		// realm synced before the variable was set still holds the client id.
		setEnv({
			...GOOD,
			PORTAL_SERVICE_CLIENT_ID: 'acme-portal',
			PORTAL_SERVICE_CLIENT_SECRET: 'acme-portal',
		});
		const { buildPortalGuard } = await load();
		expect(() => buildPortalGuard().enforce()).toThrow(/equals the client id/);
	});

	it('refuses a plain-http issuer — the JWKS comes from there', async () => {
		setEnv({ ...GOOD, KEYCLOAK_ISSUER_URL: 'http://keycloak.internal/realms/ds' });
		const { buildPortalGuard } = await load();
		expect(() => buildPortalGuard().enforce()).toThrow(/is not https/);
	});

	it('reports every violation at once, not one deploy at a time', async () => {
		setEnv({
			DS_ENV: 'production',
			PORTAL_SERVICE_CLIENT_ID: 'svc-ds-portal',
			KEYCLOAK_ISSUER_URL: 'http://keycloak.internal/realms/ds',
		});
		const { buildPortalGuard } = await load();
		let message = '';
		try {
			buildPortalGuard().enforce();
		} catch (e) {
			message = (e as Error).message;
		}
		expect(message).toMatch(/PORTAL_SERVICE_CLIENT_SECRET/);
		expect(message).toMatch(/KEYCLOAK_ISSUER_URL/);
	});

	it('warns instead of throwing in dev, which is what compose declares', async () => {
		const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
		setEnv({ DS_ENV: 'dev', PORTAL_SERVICE_CLIENT_ID: 'svc-ds-portal' });
		const { buildPortalGuard } = await load();
		expect(() => buildPortalGuard().enforce()).not.toThrow();
		expect(warn).toHaveBeenCalled();
		expect(warn.mock.calls[0][0]).toMatch(/PORTAL_SERVICE_CLIENT_SECRET/);
	});

	it('says nothing when there is nothing to say', async () => {
		const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
		setEnv({ ...GOOD, DS_ENV: 'dev' });
		const { buildPortalGuard } = await load();
		buildPortalGuard().enforce();
		expect(warn).not.toHaveBeenCalled();
	});
});
