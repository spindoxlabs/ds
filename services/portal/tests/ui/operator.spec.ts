import { expect, test, type Page } from '@playwright/test';
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

	/**
	 * An organisation that has applied and been verified, created by this test.
	 *
	 * **Every journey makes its own.** The onboarding queue lists *applications*,
	 * not owners, so the seeded organisations are not on it — and reaching for
	 * whichever article came first made a test assert against whatever the
	 * previous run had left behind, including organisations an earlier journey
	 * had suspended (`PT-11`).
	 */
	async function verifiedOrganisation(page: Page): Promise<string> {
		const alias = stamp();
		await page.goto('/admin/onboarding');
		await page.getByPlaceholder('who it is for').fill(`journey ${alias}`);
		await page.getByRole('button', { name: 'Issue code' }).click();
		const code = await page
			.locator('p.font-mono')
			.first()
			.textContent()
			.then((t) => t?.trim() ?? '');
		expect(code, 'the invite code is shown once, at issue time').toBeTruthy();

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

		await page.goto('/admin/onboarding?status=pending');
		const application = page.locator('article').filter({ hasText: alias }).first();
		await expect(application).toBeVisible();
		await application.locator('[name="evidence_ref"]').fill(`verified-${alias}`);
		await application.getByRole('button', { name: 'Verify' }).click();
		await page.waitForLoadState('networkidle');

		// A `did:web` too: the bundle is addressed to an identity, and an
		// organisation that applied through the public route has none — it is
		// standing up a deployment, not migrating one. Without this the bundle
		// is a 422 that reads as a broken page.
		await page.goto('/admin/onboarding?status=verified');
		const verified = page.locator('article').filter({ hasText: alias }).first();
		await verified.locator('[name="did"]').fill(`did:web:${alias}.dataspaces.localhost`);
		await verified.getByRole('button', { name: 'Set DID' }).click();
		await page.waitForLoadState('networkidle');
		return alias;
	}

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

		// 7. **The operator's chain ends here** (`DID-09`, `P-20`).
		//
		// It used to end at *issue the credential, then promote*. It cannot any
		// more: the anchor mints nothing, so a `did:web` an operator assigned is
		// not an identity anybody can issue to — the organisation generates its
		// own key and proves control of it by enrolling. What the operator hands
		// over is a single-use code, and the credential is issued when it is
		// presented.
		//
		// The page has to *say* that. Offering the button anyway produced a 409
		// with nothing on screen explaining what was missing, which is how this
		// journey found the gap.
		const awaiting = page.locator('article').filter({ hasText: alias }).first();
		await expect(awaiting.getByText(/has not enrolled yet/i).first()).toBeVisible();

		// 8. The bundle is the handover: it carries the enrolment code.
		await expect(
			awaiting.getByRole('button', { name: /Generate connection bundle/i }),
		).toBeVisible();
	});

	test('the registry is current the moment a promotion lands', async ({ page }) => {
		await login(page, 'operator');

		// **Asserted once, and that is the point** (`PT-11`). This used to poll
		// for 90 seconds, waiting out the connector's participant-registry cache
		// TTL: for up to a minute the operator console showed a registry without
		// a participant that was already in it, which is indistinguishable from
		// the promote having failed.
		//
		// The fix was at the source — a change to the registry tells every
		// configured connector to drop its cached list
		// (`identity_registry.services.registry_notify`). A poll left in place
		// after that would hide the regression it was written for: invalidation
		// silently stopping would look exactly like a slow page.
		await page.goto('/admin/participants');
		await expect(page.getByText('rec.dataspaces.localhost').first()).toBeVisible({
			timeout: 10_000,
		});
	});

	test('the bundle offers all three artefacts from one rotation', async ({ page }) => {
		await login(page, 'operator');
		const alias = await verifiedOrganisation(page);
		await page.goto('/admin/onboarding?status=verified');

		// **A named organisation, not `.first()`** — and the difference is not
		// style. The page also lists organisations an earlier run left
		// *suspended*, and a bundle carries a single-use enrolment code, which
		// only a verified organisation may be handed. Taking whichever article
		// came first made this test assert against whatever the previous run had
		// done. `example-org` is seeded and verified.
		//
		// **Asserted, not skipped** (`PT-11`): this used to `test.skip` when no
		// bundle button was on the page, which can only happen when the seed did
		// not run or the page is not rendering — turning a broken fixture into a
		// green suite.
		const mine = page.locator('article').filter({ hasText: alias }).first();
		const bundleButton = mine.getByRole('button', { name: /Generate connection bundle/i });
		await expect(
			bundleButton,
			'this test verified this organisation; no bundle control means the page is broken',
		).toBeVisible();

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
