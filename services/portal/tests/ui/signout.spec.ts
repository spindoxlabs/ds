import { expect, test } from '@playwright/test';
import { login, navLabels } from './fixtures';

/**
 * `REV-04` — signing out must end the **Keycloak** session, not only the cookie.
 *
 * ## Why this has to be a live journey
 *
 * `tests/unit/signout.test.ts` pins the URL the portal builds. It cannot prove
 * the thing that was actually broken, because the defect was never a wrong URL:
 * the redirect chain was written in the Caddyfile, twice, on paths neither mode
 * took, and in the cluster it was not written anywhere. Every unit test of every
 * component involved would have passed throughout — the ledger's recurring
 * finding, one layer out.
 *
 * So the assertion here is the user-visible property and nothing smaller:
 * **after signing out, coming back must ask who you are.** That is what fails
 * against the old code — the proxy cookie was gone, so the browser was bounced
 * to Keycloak, which still held the SSO session and issued a fresh one without
 * a prompt. The user saw the portal reload, still signed in.
 *
 * Landing on `/realms/` is therefore not enough to assert: the old behaviour
 * *also* passed through Keycloak. It is the **login form** that distinguishes a
 * real sign-out from a silent re-authentication.
 */
test.describe('sign-out ends both sessions', () => {
	test('signing out and returning asks for credentials again', async ({ page }) => {
		await login(page, 'subject');

		await page.getByRole('button', { name: 'Sign out' }).click();

		// The chain is portal → Keycloak end_session → proxy /oauth2/sign_out, and
		// the browser may settle on either the proxy's confirmation or the portal.
		// Which one is not the subject of this test, so it is not asserted; what
		// matters is the state left behind.
		await page.waitForLoadState('networkidle');

		await page.goto('/');

		// The whole defect, in one assertion. With the SSO session still alive
		// Keycloak redirects straight back with a new cookie and no form, so the
		// password field never appears.
		await expect(page.locator('#username, #password').first()).toBeVisible({
			timeout: 30_000,
		});
		await expect(page.getByRole('button', { name: 'Sign out' })).toHaveCount(0);
	});

	test('a second person can sign in afterwards without clearing browser state', async ({
		page,
	}) => {
		// The practical consequence of the same bug, and the one users report: on a
		// shared browser the "previous" identity survives sign-out, so the next
		// person silently inherits the session — including their VC-gated pages.
		await login(page, 'subject');
		await page.getByRole('button', { name: 'Sign out' }).click();
		await page.waitForLoadState('networkidle');

		await login(page, 'provider');

		// `login()` already waits for the portal and the Sign out control; this
		// asserts *whose* session it is. The nav is the portal's own answer to
		// "who am I" and the two fixtures differ in it by construction, which is
		// more robust than the displayed name — that falls back through three
		// claims. Against the old behaviour the second `login()` never saw a form,
		// so the subject's session survived and `My Consents` would still be here.
		const nav = await navLabels(page);
		expect(nav).toContain('Provider');
		expect(nav).not.toContain('My Consents');
	});
});
