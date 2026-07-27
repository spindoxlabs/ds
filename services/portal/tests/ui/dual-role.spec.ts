import { expect, test } from '@playwright/test';
import { expectReachable, login, navLabels } from './fixtures';

/**
 * One person, two credentials.
 *
 * Roles are additive, not exclusive: the same human can be a data subject about
 * their own consumption and a consumer user acting for an organisation. The
 * identity registry used to return only the most recently issued credential, and
 * the portal used to store a single `userVcRole` — so whichever VC happened to be
 * newer decided which half of the product the person could see, and the other
 * half returned 403 with no explanation.
 *
 * This journey is the one that fails first if that assumption comes back.
 */
test.describe('a user holding both credentials', () => {
	test.beforeEach(async ({ page }) => {
		await login(page, 'dual');
	});

	test('sees both sets of sections at once', async ({ page }) => {
		const nav = await navLabels(page);
		expect(nav, 'the subject sections').toContain('My Data');
		expect(nav, 'the subject sections').toContain('My Consents');
		expect(nav, 'the consumer sections').toContain('Consumer');
	});

	test('reaches both paths in a single session', async ({ page }) => {
		// The decisive assertion: each call must present the credential matching
		// the role *that call* needs, not whichever one resolution returned. A 403
		// on either page means the wrong VC was sent.
		await expectReachable(page, '/my-data');
		await expect(page.getByRole('heading', { name: 'My Data' })).toBeVisible();

		await expectReachable(page, '/consumer');
		await expect(page.getByRole('heading', { name: 'Consumer' })).toBeVisible();

		// And back again, in the same session — proving neither visit invalidated
		// the other's credential selection.
		await expectReachable(page, '/consent');
		await expectReachable(page, '/consumer');
	});

	test('is not redirected away from either landing page', async ({ page }) => {
		// The landing page used to redirect by role *priority*, which bounced a
		// dual-role user away from whichever path lost the tie.
		await page.goto('/');
		const url = new URL(page.url());
		expect(['/', '/my-data', '/consumer']).toContain(url.pathname);
		// Whatever it chose, the other section is still one click away.
		const nav = await navLabels(page);
		expect(nav.length).toBeGreaterThan(1);
	});
});
