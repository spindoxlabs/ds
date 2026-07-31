import { defineConfig, devices } from '@playwright/test';

/**
 * UI journeys against a *running* stack.
 *
 * There is deliberately no `webServer`: every journey needs the connector, the
 * identity registry, provenance and Keycloak as well as the portal, so starting
 * a dev server here would produce a portal with nothing behind it. Bring the
 * stack up first (`task docker:start` or `task dev:start`) — `global-setup.ts`
 * fails with that instruction rather than letting the suite red out on timeouts.
 *
 * Auth is real: each journey signs in through the Keycloak login form with a dev
 * realm user. Mocking the session would remove the part most worth testing — the
 * portal's whole authorisation model is derived from the token and the user's
 * credentials, so a faked session tests the mock.
 */
const PORTAL_URL = process.env.PORTAL_URL ?? 'http://portal.dataspaces.localhost';

export default defineConfig({
	testDir: './tests/ui',
	globalSetup: './tests/ui/global-setup.ts',
	// Journeys mutate shared backend state (consent rows, onboarding applications),
	// so they run one at a time. Parallelism here would trade a real signal for a
	// flaky one.
	workers: 1,
	fullyParallel: false,
	forbidOnly: !!process.env.CI,
	retries: 0,
	timeout: 90_000,
	expect: { timeout: 15_000 },
	reporter: process.env.CI ? [['github'], ['list']] : [['list']],
	use: {
		baseURL: PORTAL_URL,
		trace: 'retain-on-failure',
		screenshot: 'only-on-failure',
		actionTimeout: 15_000,
	},
	projects: [
		{ name: 'chromium', use: { ...devices['Desktop Chrome'] } },
	],
});
