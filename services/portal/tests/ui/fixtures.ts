import { expect, type Page } from '@playwright/test';

/**
 * Dev-realm users, from `services/keycloak/realm-dataspaces-dev.json`.
 *
 * Two independent axes decide what each one may do, and the journeys exist
 * largely to prove they stay independent:
 *
 * - **Keycloak groups** grant service permissions (`connector.provider.*`,
 *   `identity-registry.organizations.*`). `provider` and `operator` are these.
 * - **Verifiable credentials** issued by the identity registry decide the
 *   person-facing roles (`ConsumerUser`, `DataSubject`). `consumer`, `subject`
 *   and `dual` are these.
 *
 * `dual` holds *both* VC roles. It is the fixture that catches any code path
 * that still assumes one role per person.
 */
export const USERS = {
	operator: { username: 'admin@example.test', password: 'admin' },
	provider: { username: 'provider@example.test', password: 'provider' },
	consumer: { username: 'consumer@example.test', password: 'consumer' },
	subject: { username: 'subject@example.test', password: 'subject' },
	dual: { username: 'dual@example.test', password: 'dual' },
} as const;

export type Role = keyof typeof USERS;

/**
 * Sign in the way a person does — through the Keycloak form.
 *
 * Not via a seeded cookie or a direct-grant token: the portal derives every
 * authorisation decision from the resulting session, so a fabricated one would
 * make the journeys assert against the fixture instead of the product.
 *
 * There is no "Sign in" button to click any more. The portal sits behind
 * oauth2-proxy, so Caddy answers an unauthenticated request with a redirect to
 * Keycloak before the portal renders anything — navigating *is* the sign-in.
 */
export async function login(page: Page, role: Role): Promise<void> {
	const user = USERS[role];
	await page.goto('/');

	await page.waitForURL(/\/realms\/dataspaces\//, { timeout: 30_000 });

	// The dev realm uses identity-first login: email, then password on a second
	// page. Handled as two conditional steps rather than assumed, so the helper
	// survives a realm configured either way.
	const username = page.locator('#username');
	if (await username.isVisible()) {
		await username.fill(user.username);
		if (!(await page.locator('#password').isVisible())) {
			await page.locator('#kc-login').click();
			await page.locator('#password').waitFor({ timeout: 15_000 });
		}
	}
	await page.locator('#password').fill(user.password);
	await page.locator('#kc-login').click();

	// Back on the portal, authenticated: the sign-out control is the portal's own
	// statement that it accepted the session.
	await page.waitForURL((url) => !url.pathname.includes('/realms/'), { timeout: 30_000 });
	await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
}

/** Nav entries currently offered — the portal's own answer to "who am I". */
export async function navLabels(page: Page): Promise<string[]> {
	const links = page.locator('header nav').first().getByRole('link');
	return (await links.allTextContents()).map((t) => t.trim()).filter(Boolean);
}

/**
 * Assert a route is *reachable*, not merely that it renders.
 *
 * A 403 in this portal renders as an explanation rather than a redirect (by
 * design — a silent bounce makes a missing group look like a broken page), so
 * "the page loaded" is not evidence of access. This checks the response status
 * and that no refusal was rendered.
 */
export async function expectReachable(page: Page, path: string): Promise<void> {
	const response = await page.goto(path);
	expect(response?.status(), `${path} should be reachable`).toBeLessThan(400);
	await expect(
		page.getByText(/not permitted|forbidden|missing permission/i),
	).toHaveCount(0);
}

export async function expectRefused(page: Page, path: string): Promise<void> {
	const response = await page.goto(path);
	const status = response?.status() ?? 0;
	if (status < 400) {
		// A 200 that renders the refusal is the portal's documented shape for a
		// missing grant; anything else means the guard did not run.
		await expect(
			page.getByText(/not permitted|forbidden|missing permission|sign in/i).first(),
		).toBeVisible();
	}
}
