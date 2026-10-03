/**
 * The portal's `ProductionGuard` — `AUTH-04`.
 *
 * Every Python service builds one of these at startup, registers its dangerous
 * dev defaults, and unless `DS_ENV=dev` logs every violation and refuses
 * to start (`libs/ds-auth/src/ds_auth/production.py`). The portal had no
 * equivalent, so `PORTAL_SERVICE_CLIENT_SECRET` fell back to the client id
 * behind a one-time `console.warn` — a line in a log nobody reads, on the
 * credential that lets the portal call the identity registry as a service.
 *
 * Deliberately mirrored rather than shared: there is no Python runtime here, and
 * the root guide's rule is that a new dev default is registered with the guard
 * **in the same change**. That rule needs a guard on this side to be followable.
 *
 * ## Two details that are not free choices
 *
 * **Only `DS_ENV=dev` relaxes**, exactly as `ds_auth.is_production` decides.
 * Unset, empty (`${DS_ENV:-}` in compose renders `""`), `production`, `prod`,
 * `staging`, `test`, a typo — every value but `dev` is production. Comparing
 * against the exact string `production` meant any other value disarmed the
 * guard, and the whole point is that forgetting (or misspelling) is the safe
 * direction. `docker-compose.yml` and the dev tasks set `DS_ENV=dev`
 * explicitly, which is the declaration this asks for.
 *
 * `enforce()` **throws**, and it is called at module scope from
 * `hooks.server.ts`, so a misconfigured production portal fails to boot rather
 * than serving pages that 401 against every upstream. A guard that let the
 * process start would reproduce the defect it replaces.
 */
import { env } from '$env/dynamic/private';

/** The one value that relaxes the guard (compared after trim + lowercase). */
const DEV = 'dev';
/** What an unset or empty `DS_ENV` reads as. */
const PRODUCTION = 'production';

/**
 * Values never acceptable as a secret, whatever the setting is named — the same
 * list as `ds_auth.production.UNIVERSAL_WEAK_VALUES`.
 */
export const UNIVERSAL_WEAK_VALUES: ReadonlySet<string> = new Set([
	'',
	'admin',
	'changeme',
	'change-me',
	'password',
	'postgres',
	'secret',
	'test',
]);

/** Trim + lowercase; unset and empty both read as `production`. */
export function normaliseEnv(value: string | undefined | null): string {
	const text = (value ?? '').trim().toLowerCase();
	return text || PRODUCTION;
}

export function currentEnv(): string {
	return normaliseEnv(env.DS_ENV);
}

/** True unless `DS_ENV` is exactly `dev` — every other value is production. */
export function isProduction(): boolean {
	return currentEnv() !== DEV;
}

export class InsecureProductionConfig extends Error {}

export interface Violation {
	setting: string;
	problem: string;
	remediation: string;
}

export class ProductionGuard {
	readonly violations: Violation[] = [];
	private readonly envName: string;

	constructor(
		private readonly service: string,
		envName: string = currentEnv(),
	) {
		this.envName = normaliseEnv(envName);
	}

	/** True unless this guard's environment is exactly `dev`. */
	get isProduction(): boolean {
		return this.envName !== DEV;
	}

	add(setting: string, problem: string, remediation: string): void {
		this.violations.push({ setting, problem, remediation });
	}

	/** Flag a setting production cannot run without. */
	requireSet(setting: string, value: unknown, remediation: string): void {
		if (value === undefined || value === null || String(value).trim() === '') {
			this.add(setting, 'is not set', remediation);
		}
	}

	/**
	 * Flag a value still equal to one of the shipped dev defaults, or trivially
	 * weak (`UNIVERSAL_WEAK_VALUES`) — the same two checks as the Python guard's
	 * `forbid_default`. An absent value (`undefined`/`null`) is `requireSet`'s
	 * job and is not reported here.
	 */
	forbidDefault(
		setting: string,
		value: unknown,
		insecureDefaults: Iterable<string>,
		remediation: string,
	): void {
		if (value === undefined || value === null) return;
		const text = String(value).trim();
		if (text && [...insecureDefaults].includes(text)) {
			this.add(setting, `is still the development default (${text})`, remediation);
		} else if (UNIVERSAL_WEAK_VALUES.has(text.toLowerCase())) {
			this.add(setting, 'is set to a trivially weak value', remediation);
		}
	}

	/**
	 * Flag a secret equal to the client id it belongs to.
	 *
	 * Catches what `forbidDefault` cannot: a deployment that renamed the client
	 * and left the secret matching the new name, and — the case `KC-01` records —
	 * a realm synced before the variable was set, since `keycloak sync` applies a
	 * secret on create only.
	 */
	forbidSecretEqualToClientId(
		setting: string,
		clientId: unknown,
		secret: unknown,
		remediation: string,
	): void {
		const id = String(clientId ?? '').trim();
		const value = String(secret ?? '').trim();
		if (id && value && id === value) {
			this.add(setting, `equals the client id (${id})`, remediation);
		}
	}

	/** Flag a URL that is not https:// — same rule as the Python guard's. */
	requireHttps(setting: string, value: unknown, remediation: string): void {
		if (value === undefined || value === null) return;
		const text = String(value).trim();
		if (text && !text.startsWith('https://')) {
			this.add(setting, `is not https (${text})`, remediation);
		}
	}

	/** Warn under `DS_ENV=dev`; throw under every other value. Safe with no violations. */
	enforce(): void {
		if (this.violations.length === 0) return;

		const lines = this.violations.map(
			(v) => `  - ${v.setting} ${v.problem}. ${v.remediation}`,
		);
		const summary = `[${this.service}] insecure configuration:\n${lines.join('\n')}`;

		if (this.isProduction) {
			throw new InsecureProductionConfig(
				`${summary}\n\nRefusing to start with DS_ENV=${JSON.stringify(this.envName)} ` +
					'(only DS_ENV=dev relaxes this guard; unset, empty or any other value ' +
					'is production).',
			);
		}
		console.warn(`${summary}\n\n(DS_ENV=${this.envName}, so this is a warning.)`);
	}
}

/** The portal's own dangerous defaults, in one place. */
export function buildPortalGuard(): ProductionGuard {
	const guard = new ProductionGuard('ds-portal');
	const clientId = env.PORTAL_SERVICE_CLIENT_ID ?? 'svc-ds-portal';

	guard.requireSet(
		'PORTAL_SERVICE_CLIENT_SECRET',
		env.PORTAL_SERVICE_CLIENT_SECRET,
		'Set the Keycloak client secret for the portal service account. Unset, the ' +
			'portal authenticates to the identity registry with the client id as its ' +
			'secret, which the dev realm accepts and no other realm should.',
	);
	guard.forbidDefault(
		'PORTAL_SERVICE_CLIENT_SECRET',
		env.PORTAL_SERVICE_CLIENT_SECRET,
		['svc-ds-portal'],
		'Set a real secret for the portal service account.',
	);
	guard.forbidSecretEqualToClientId(
		'PORTAL_SERVICE_CLIENT_SECRET',
		clientId,
		env.PORTAL_SERVICE_CLIENT_SECRET,
		'Set a real secret AND make sure the realm holds it — a realm synced ' +
			'before the variable was set still has the client id (KC-01).',
	);
	// The issuer the portal fetches its JWKS from, and asks for service tokens
	// at. Same rule the four Python services now register (AUTH-06). Not
	// `requireSet`: `resolveIssuer()` already throws on an unset issuer, and
	// duplicating that here would report it twice with two different messages.
	guard.requireHttps(
		'KEYCLOAK_ISSUER_URL',
		env.KEYCLOAK_ISSUER_URL,
		"Use an https:// issuer URL; the realm's JWKS is fetched from it.",
	);
	return guard;
}
