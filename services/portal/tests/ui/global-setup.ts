/**
 * Fail fast, and say what is missing.
 *
 * Without this, a stack that is down produces a wall of 90-second navigation
 * timeouts that reads like a broken portal rather than a portal that was never
 * started.
 */
const PORTAL_URL = process.env.PORTAL_URL ?? 'http://portal.dataspaces.localhost:9010';
const KEYCLOAK_URL =
	process.env.KEYCLOAK_URL ?? 'http://keycloak.dataspaces.localhost:9010';

async function reachable(url: string): Promise<string | null> {
	try {
		const r = await fetch(url, { signal: AbortSignal.timeout(5000) });
		return r.status < 500 ? null : `${url} answered ${r.status}`;
	} catch (e) {
		return `${url} is unreachable (${e instanceof Error ? e.message : e})`;
	}
}

export default async function globalSetup() {
	const problems = (
		await Promise.all([
			reachable(PORTAL_URL),
			reachable(`${KEYCLOAK_URL}/realms/dataspaces/.well-known/openid-configuration`),
		])
	).filter(Boolean);

	if (problems.length) {
		throw new Error(
			`The UI journeys need a running stack.\n  ${problems.join('\n  ')}\n\n` +
				'Start it with `task docker:start` (full) or `task dev:start` (fast), then retry.',
		);
	}
}
