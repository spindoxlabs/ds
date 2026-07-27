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
