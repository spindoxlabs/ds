import { expect, test } from '@playwright/test';
import { expectReachable, login } from './fixtures';

/**
 * The holder reads the keys its own connector serves (ADR-0022).
 *
 * The page is shown on `connector.consent.holder.read` or `connector.admin`.
 * The operator holds the second; the producer holds provider grants only, and
 * the holder permission is deliberately in no bundle — so the producer reaches
 * the provider section but not this page, and has to be told why.
 */
test.describe('authorised keys', () => {
	test('the operator sees the current list and the history of an offer', async ({ page }) => {
		await login(page, 'operator');
		await expectReachable(page, '/provider/keys');
		await expect(page.getByRole('heading', { name: 'Authorised keys' })).toBeVisible();

		// The rec connector serves consent-based offers, so there is one to show.
		// No offer selector here would mean the offers read failed or was filtered
		// to nothing — both a broken page, not an empty one.
		const offers = page.getByLabel('Sharing offer').getByRole('link');
		await expect(offers.first()).toBeVisible();
		// A connector error renders as a banner on an otherwise normal page.
		await expect(page.getByText(/could not (read|reach)|refused|not permitted/i)).toHaveCount(0);

		const current = page.getByRole('tab', { name: 'Authorised now' });
		const history = page.getByRole('tab', { name: 'History' });
		await expect(current).toHaveAttribute('aria-selected', 'true');
		// Either the key table or the stated empty list — the connector answered.
		await expect(
			page.getByTestId('holder-keys').or(page.getByText('No key is authorised under this offer.')),
		).toBeVisible();
		await expect(page.getByTestId('key-count').first()).toBeVisible();

		await history.click();
		await expect(page).toHaveURL(/tab=history/);
		await expect(page.getByRole('tab', { name: 'History' })).toHaveAttribute('aria-selected', 'true');
		await expect(page.getByText(/could not (read|reach)|refused|not permitted/i)).toHaveCount(0);
		// The history states where the ledger starts, whatever it holds.
		await expect(
			page
				.getByTestId('holder-key-events')
				.or(page.getByText('Nothing has happened under this offer yet.')),
		).toBeVisible();
	});

	test('a producer without the holder permission is told what is missing', async ({ page }) => {
		await login(page, 'provider');
		// The provider section itself is open to them …
		await expectReachable(page, '/provider');
		// … this page is not, and the refusal names the permission rather than
		// bouncing to a page that looks broken.
		const response = await page.goto('/provider/keys');
		expect(response?.status()).toBe(403);
		await expect(
			page.getByRole('heading', { name: 'You do not have access to this page' }),
		).toBeVisible();
		await expect(page.getByText(/connector\.consent\.holder\.read/).first()).toBeVisible();
		await expect(page.getByTestId('holder-keys')).toHaveCount(0);
	});
});
