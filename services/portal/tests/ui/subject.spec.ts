import { expect, test } from '@playwright/test';
import { login } from './fixtures';

/**
 * The data subject's path: see what is asked of them, decide, and see the record
 * of that decision.
 *
 * Assertions are on state that survives a reload — the page is server-rendered
 * from the connector, so a decision still present after `reload()` is evidence
 * the API wrote it, not that a component re-rendered optimistically.
 */
test.describe('data subject', () => {
	test.beforeEach(async ({ page }) => {
		await login(page, 'subject');
	});

	test('offers are rendered from the published vocabulary', async ({ page }) => {
		await page.goto('/my-data');
		await expect(page.getByRole('heading', { name: 'My Data' })).toBeVisible();

		// The subject DID, not an internal user id: the connector keys consent on it.
		await expect(page.locator('code').first()).toContainText('did:web:');

		const offers = page.locator('section', { has: page.getByRole('heading', { name: 'Sharing' }) })
			.locator('article');
		expect(await offers.count(), 'the dev stack publishes sharing offers').toBeGreaterThan(0);
	});

	test('a contract-based offer is disclosed, never toggled', async ({ page }) => {
		await page.goto('/my-data');
		const contractual = page.locator('article', {
			has: page.getByText('required by contract'),
		});
		// Presenting a choice that does not exist is what invalidates consent, so
		// where one is absent the page must say so instead of showing a control.
		for (const article of await contractual.all()) {
			await expect(article.getByRole('button', { name: /Share|Stop sharing/ })).toHaveCount(0);
			await expect(article.getByText(/No choice to make/)).toBeVisible();
		}
	});

	test('granting and withdrawing both persist, and the grant carries its record', async ({
		page,
	}) => {
		await page.goto('/my-data');

		// **The precondition is made true, not skipped over** (`PT-11`). This used
		// to `test.skip` when every offer was already granted — which is the
		// state a previous run leaves behind, so on a re-run the one journey that
		// proves consent works simply did not run, and the suite stayed green
		// having tested nothing.
		//
		// A subject can always withdraw, so the precondition is reachable: stop
		// sharing one offer, then grant it. That also means this journey no
		// longer depends on what any earlier run did.
		let share = page.getByRole('button', { name: 'Share', exact: true }).first();
		if ((await share.count()) === 0) {
			const granted = page.getByRole('button', { name: 'Stop sharing' }).first();
			await expect(
				granted,
				'a subject with neither a grantable nor a withdrawable offer has no choice at all',
			).toBeVisible();
			await granted.click();
			await page.waitForLoadState('networkidle');
			await page.reload();
			share = page.getByRole('button', { name: 'Share', exact: true }).first();
		}
		const article = page.locator('article').filter({ has: share }).first();
		const purpose = (await article.getByRole('heading').first().textContent())?.trim() ?? '';

		await share.click();
		await page.waitForLoadState('networkidle');

		const granted = page.locator('article').filter({ hasText: purpose }).first();
		await expect(granted.getByRole('button', { name: 'Stop sharing' })).toBeVisible();

		// Art. 7(1): the decision must come with evidence of what was agreed to.
		await expect(granted.getByText('Record of this decision')).toBeVisible();
		await granted.getByText('Record of this decision').click();
		await expect(granted.getByText('Fingerprint of what you were shown:')).toBeVisible();

		// It survives a reload, so the connector holds it.
		await page.reload();
		const afterReload = page.locator('article').filter({ hasText: purpose }).first();
		await expect(afterReload.getByRole('button', { name: 'Stop sharing' })).toBeVisible();

		// Withdrawal must be at least as easy as granting.
		await afterReload.getByRole('button', { name: 'Stop sharing' }).click();
		await page.waitForLoadState('networkidle');
		await page.reload();
		await expect(
			page.locator('article').filter({ hasText: purpose }).first()
				.getByRole('button', { name: 'Share', exact: true }),
		).toBeVisible();
	});

	test('the decision appears in the subject-authenticated timeline', async ({ page }) => {
		await page.goto('/my-data');
		const timeline = page.locator('section', {
			has: page.getByRole('heading', { name: 'What happened with your data' }),
		});
		await expect(timeline).toBeVisible();
		// Read with the subject's own credential from /prov/my/events. An error
		// banner here means the VC-JWT path is broken, which an empty list hides.
		await expect(timeline.getByText(/could not|error/i)).toHaveCount(0);
	});
});
