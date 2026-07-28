import { expect, test } from '@playwright/test';
import { expectRefused, login } from './fixtures';

/**
 * The operator's path, end to end: issue an invite, watch a third party apply
 * through the public route, then walk the gates — verify, agreement, credential,
 * promote — and hand over a connection bundle.
 *
 * Each organisation is unique per run, so the journey never depends on, and never
 * corrupts, the state another run left behind.
 */
const stamp = () => `e2e${Date.now().toString(36)}`;

test.describe('operator', () => {
	test('the onboarding queue and observability are reachable', async ({ page }) => {
		await login(page, 'operator');
		await page.goto('/admin/onboarding');
		await expect(page.getByRole('heading', { name: 'Organisation onboarding' })).toBeVisible();
		await page.goto('/admin/observability');
		await expect(page.getByRole('heading', { name: 'Observability' })).toBeVisible();
		await page.goto('/admin/agreements');
		await expect(page.getByRole('heading', { name: /Agreements/i })).toBeVisible();
	});

	test('a third party joins by invite and is walked through every gate', async ({ page }) => {
		const alias = stamp();
		await login(page, 'operator');

		// 1. The operator issues a single-use code.
		await page.goto('/admin/onboarding');
		await page.getByPlaceholder('who it is for').fill(`journey ${alias}`);
		await page.getByRole('button', { name: 'Issue code' }).click();
		const code = await page
			.locator('p.font-mono')
			.first()
			.textContent()
			.then((t) => t?.trim() ?? '');
		expect(code, 'the invite code is shown once, at issue time').toBeTruthy();

		// 2. The applicant uses the public route. Signed out on purpose: the whole
		//    point of an invite is that applying needs no account here.
		const applicant = await page.context().browser()!.newContext();
		const applicantPage = await applicant.newPage();
		await applicantPage.goto(`${test.info().project.use.baseURL}/join?code=${code}`);
		await applicantPage.locator('[name="legal_name"]').fill(`Journey Org ${alias}`);
		await applicantPage.locator('[name="alias"]').fill(alias);
		await applicantPage.locator('[name="invite_code"]').fill(code);
		await applicantPage.locator('[name="legal_country_code"]').fill('IT');
		await applicantPage.locator('[name="evidence_ref"]').fill(`ticket-${alias}`);
		await applicantPage.getByRole('button', { name: /Apply|Submit|Send/i }).click();
		await expect(applicantPage.getByText('Application received')).toBeVisible();
		await applicant.close();

		// 3. It appears in the operator's queue.
		await page.goto('/admin/onboarding?status=pending');
		const application = page.locator('article').filter({ hasText: alias }).first();
		await expect(application).toBeVisible();

		// 4. Verify — an offline judgement, recorded by reference, never a document.
		await application.locator('[name="evidence_ref"]').fill(`verified-${alias}`);
		await application.getByRole('button', { name: 'Verify' }).click();
		await page.waitForLoadState('networkidle');

		// 5. The gates are stated, not hidden: before an agreement is accepted the
		//    page must say why a credential cannot be issued.
		await page.goto('/admin/onboarding?status=verified');
		const verified = page.locator('article').filter({ hasText: alias }).first();
		await expect(verified.getByText(/agreement/i).first()).toBeVisible();

		// 6. Accept an agreement, then issue the credential the promotion needs.
		const agreement = verified.locator('[name="agreement"]');
		await agreement.selectOption({ index: 1 });
		await verified.getByRole('button', { name: /Accept/i }).click();
		await page.waitForLoadState('networkidle');

		// The credential is issued against a `did:web`, and an organisation that
		// applied through the public route has none — it is standing up a
		// deployment, not migrating one. The operator assigns it here; without
		// this control the gate could never be satisfied from the portal.
		const needsDid = page.locator('article').filter({ hasText: alias }).first();
		await needsDid.locator('[name="did"]').fill(`did:web:${alias}.dataspaces.localhost`);
		await needsDid.getByRole('button', { name: 'Set DID' }).click();
		await page.waitForLoadState('networkidle');

		const withAgreement = page.locator('article').filter({ hasText: alias }).first();
		await withAgreement.getByRole('button', { name: /Issue/i }).click();
		await page.waitForLoadState('networkidle');

		// 7. Promote — the irreversible act that makes them a DSP counterparty.
		const promotable = page.locator('article').filter({ hasText: alias }).first();
		await promotable.locator('[name="dsp_address"]').fill('http://172.17.0.1:39194/protocol/2025-1');
		await promotable.getByRole('button', { name: /Promote/i }).click();
		await page.waitForLoadState('networkidle');

		// 8. The participant is now in the registry — the effect that matters.
		//
		// Polled, not asserted once: the connector caches the participant
		// registry for `CONNECTOR_PARTICIPANT_REGISTRY_CACHE_TTL` (60s by
		// default), so a promote is not visible on this page immediately. A
		// single 15s assertion made this test a coin flip on how recently
		// anything else had read the registry.
		//
		// **The staleness is real, not a test artefact**: for up to the TTL the
		// operator console shows a registry without the participant an operator
		// just created. Worth fixing at the source — invalidate on promote —
		// rather than only waiting here.
		await expect(async () => {
			await page.goto('/admin/participants');
			await expect(page.getByText(alias, { exact: false }).first()).toBeVisible({
				timeout: 2_000,
			});
		}).toPass({ timeout: 90_000 });
	});

	test('the bundle offers all three artefacts from one rotation', async ({ page }) => {
		await login(page, 'operator');
		await page.goto('/admin/onboarding?status=verified');

		const bundleButton = page.getByRole('button', { name: /Generate connection bundle/i }).first();
		test.skip((await bundleButton.count()) === 0, 'no promoted organisation to issue a bundle for');

		await bundleButton.click();
		await page.waitForLoadState('networkidle');

		// One call rotates once; three separate calls would hand over two bundles
		// whose secret no longer authenticates.
		await expect(page.getByRole('button', { name: 'Download bundle.json' })).toBeVisible();
		await expect(page.getByRole('button', { name: 'Download .env' })).toBeVisible();
		await expect(page.getByRole('button', { name: 'Download .properties' })).toBeVisible();

		const download = page.waitForEvent('download');
		await page.getByRole('button', { name: 'Download .properties' }).click();
		const properties = await (await download).createReadStream();
		const text = await new Response(properties as never).text();
		expect(text).toContain('edc.participant.id=');
		// Properties files get committed; the secret belongs in the env fragment.
		expect(text).not.toMatch(/client[_.]secret\s*=\s*\S/i);
	});
});

test.describe('operator surfaces are not open to everyone', () => {
	test('a data subject cannot reach the onboarding queue', async ({ page }) => {
		await login(page, 'subject');
		await expectRefused(page, '/admin/onboarding');
	});
});
