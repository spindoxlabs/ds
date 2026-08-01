import { expect, test } from '@playwright/test';
import { expectReachable, expectRefused, login, navLabels } from './fixtures';

/**
 * The two participant-side paths.
 *
 * Producer decides what to share and on what terms; consumer asks, monitors and
 * withdraws. They are separate *axes*, not alternatives — see `dual-role.spec.ts`.
 */
test.describe('producer', () => {
	test.beforeEach(async ({ page }) => {
		await login(page, 'provider');
	});

	test('every producer section is reachable with provider grants alone', async ({ page }) => {
		// `connector.provider.read/write` and nothing else: if any of these needs
		// an admin grant, the read-only producer is locked out of their own data.
		// `/provider/governance` is deliberately absent: it had no `+page.server.ts`,
		// read nothing, and its own body pointed at Provider Assets, so it was
		// removed rather than implemented. Listing it here made this journey fail
		// on a 404 for a page nobody decided to keep.
		for (const path of [
			'/provider',
			'/provider/assets',
			'/provider/contracts',
			'/provider/requests',
			'/provider/activity',
		]) {
			await expectReachable(page, path);
		}
	});

	test('the request queue renders asks rather than failing when empty', async ({ page }) => {
		await page.goto('/provider/requests');
		await expect(page.getByRole('heading', { name: 'Consent requests' })).toBeVisible();
		// An error banner and an empty queue look identical to a passing test that
		// only checks the heading, so assert the absence of the first.
		await expect(page.getByText(/could not load|failed to/i)).toHaveCount(0);
	});

	test('a producer has no operator tooling', async ({ page }) => {
		expect(await navLabels(page)).not.toContain('Admin');
		await expectRefused(page, '/admin/onboarding');
	});
});

test.describe('consumer', () => {
	test.beforeEach(async ({ page }) => {
		await login(page, 'consumer');
	});

	test('the catalog and the consumer sections are reachable', async ({ page }) => {
		await expectReachable(page, '/');
		await expectReachable(page, '/consumer');
		await expectReachable(page, '/consumer/activity');
		await expect(page.getByRole('heading', { name: /Activity/i }).first()).toBeVisible();
	});

	test('access requests carry their state, including waiting on a person', async ({ page }) => {
		await page.goto('/consumer');
		await expect(page.getByRole('heading', { name: 'Access Requests' })).toBeVisible();
		await expect(page.getByText(/could not load|failed to/i)).toHaveCount(0);

		// `awaiting_consent` is the state that exists because a human has not yet
		// answered. Rendering it as a generic "pending" would hide the reason.
		const waiting = page.getByText(/waiting on a person|awaiting consent/i);
		if ((await waiting.count()) > 0) {
			await expect(waiting.first()).toBeVisible();
		}
	});

	test('a consumer cannot reach provider tooling', async ({ page }) => {
		expect(await navLabels(page)).not.toContain('Provider');
		await expectRefused(page, '/provider/assets');
	});
});
