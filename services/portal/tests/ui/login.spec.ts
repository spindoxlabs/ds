import { expect, test } from '@playwright/test';
import { login, navLabels } from './fixtures';

/**
 * The foundation every other journey stands on: a real Keycloak sign-in, and a
 * navigation that reflects what the person actually holds.
 */
test.describe('sign-in and role visibility', () => {
	test('an operator signs in and sees the admin section', async ({ page }) => {
		await login(page, 'operator');
		expect(await navLabels(page)).toContain('Admin');
	});

	test('a provider sees Provider and not Admin', async ({ page }) => {
		await login(page, 'provider');
		const nav = await navLabels(page);
		expect(nav).toContain('Provider');
		expect(nav).not.toContain('Admin');
	});

	test('a data subject sees their own sections and no provider tooling', async ({ page }) => {
		await login(page, 'subject');
		const nav = await navLabels(page);
		expect(nav).toContain('My Data');
		expect(nav).toContain('My Consents');
		expect(nav).not.toContain('Provider');
		expect(nav).not.toContain('Admin');
	});
});

/**
 * The auth wall's edges.
 *
 * oauth2-proxy fronts the portal, so *everything* is behind a login redirect
 * unless Caddy carves it out — and the one page that must stay public is the one
 * whose visitor has no account yet. This was a real regression: putting the proxy
 * in front sent an applicant following an invite link to a login form for an
 * account that does not exist. Asserted directly here rather than left to the
 * operator journey, which caught it only as a missing form field.
 */
test.describe('the authentication perimeter', () => {
	test('an applicant with no account reaches the invite page', async ({ browser }) => {
		const anonymous = await browser.newContext();
		const page = await anonymous.newPage();
		await page.goto('/join?code=whatever');

		// Still on the portal, and the form is rendered — not bounced to Keycloak.
		expect(new URL(page.url()).pathname).toBe('/join');
		await expect(page.locator('[name="invite_code"]')).toBeVisible();
		await anonymous.close();
	});

	test("the applicant's page arrives with its stylesheet and scripts", async ({ browser }) => {
		const anonymous = await browser.newContext();
		const page = await anonymous.newPage();

		// Reaching /join is not the same as *rendering* it: SvelteKit serves the
		// stylesheet and the entry chunks from /_app/immutable, and those requests
		// hit the same wall. Before the carve-out the page answered 200 and all
		// three assets 302'd to a login form, so the only page a stranger is meant
		// to see arrived unstyled and unscripted — invisible to an assertion that
		// only checks the URL and the form field.
		const assets: { url: string; status: number }[] = [];
		page.on('response', (r) => {
			if (r.url().includes('/_app/immutable/')) assets.push({ url: r.url(), status: r.status() });
		});

		await page.goto('/join?code=whatever');
		await page.waitForLoadState('networkidle');

		expect(assets.length).toBeGreaterThan(0);
		expect(assets.filter((a) => a.status !== 200)).toEqual([]);

		// The carve-out is /_app/immutable, not /_app. `env.js` is generated at
		// runtime from PUBLIC_* rather than built, so it stays behind the wall —
		// widening the prefix would publish it.
		const env = await page.request.get('/_app/env.js', { maxRedirects: 0 });
		expect(env.status()).toBe(302);

		await anonymous.close();
	});

	test('an anonymous browser is bounced from an authenticated page', async ({ browser }) => {
		const anonymous = await browser.newContext();
		const page = await anonymous.newPage();
		await page.goto('/provider');

		// The redirect chain ends at Keycloak, and the port survives it — a missing
		// port in redirect_url or whitelist_domains is what breaks this.
		await page.waitForURL(/\/realms\/dataspaces\//, { timeout: 30_000 });
		await expect(page.locator('#username')).toBeVisible();
		await anonymous.close();
	});
});
