import { expect, test } from '@playwright/test';
import { login } from './fixtures';

/**
 * The lineage graph view, which had no journey at all.
 *
 * That absence is how it once rendered **every node and zero edges** for months:
 * `classifyLineageGraph` split the `@graph` on keys nothing emitted, and the graph
 * draws to a canvas — so a graph with no edges looks sparse rather than broken.
 * The counts beside the heading exist to make that observable from outside the
 * canvas; the edges > 0 assertion is the standing guard against it recurring,
 * including on any future change to the provenance edge shape.
 *
 * The *direction* test is the one that was red before this pass: `downstream`
 * selected both directions, so it returned the same graph as `both`.
 *
 * Depends on a seeded exchange: run `task e2e:all` (or at least `task e2e:smoke`)
 * first, which is what puts a published dataset and its activities in the graph.
 */
const DATASET = 'datasets.silver.meters_15m';

async function counts(page: import('@playwright/test').Page) {
	const text = await page.getByTestId('lineage-counts').innerText();
	const [nodes, edges] = [...text.matchAll(/(\d+)/g)].map((m) => Number(m[1]));
	return { nodes, edges };
}

test.describe('lineage', () => {
	test.beforeEach(async ({ page }) => {
		// `ds-participant-admin` carries `provenance.read`.
		await login(page, 'provider');
	});

	test('the graph renders edges, not only nodes', async ({ page }) => {
		await page.goto(`/lineage/${encodeURIComponent(DATASET)}?direction=both&max_depth=5`);

		await expect(page.getByRole('heading', { name: 'Lineage' })).toBeVisible();
		await expect(page.getByText(/No lineage data found/i)).toHaveCount(0);
		await expect(page.locator('.bg-red-50')).toHaveCount(0);

		const { nodes, edges } = await counts(page);
		expect(nodes).toBeGreaterThan(0);
		// The defect, stated as a number: this was 0.
		expect(edges).toBeGreaterThan(0);
	});

	test('direction narrows the graph rather than returning the same one', async ({ page }) => {
		await page.goto(`/lineage/${encodeURIComponent(DATASET)}?direction=both&max_depth=5`);
		const both = await counts(page);

		await page.goto(`/lineage/${encodeURIComponent(DATASET)}?direction=upstream&max_depth=5`);
		const upstream = await counts(page);

		await page.goto(`/lineage/${encodeURIComponent(DATASET)}?direction=downstream&max_depth=5`);
		const downstream = await counts(page);

		expect(upstream.edges).toBeGreaterThan(0);
		expect(downstream.edges).toBeGreaterThan(0);
		// `downstream` used to select both directions, so it equalled `both` — the
		// filter appeared to work while answering a different question.
		expect(downstream.nodes).toBeLessThan(both.nodes);
		expect(upstream.nodes).toBeLessThan(both.nodes);
	});

	test('an unknown IRI reports no lineage instead of failing', async ({ page }) => {
		await page.goto(`/lineage/${encodeURIComponent('urn:dataset:does-not-exist')}`);
		await expect(page.getByRole('heading', { name: 'Lineage' })).toBeVisible();
		const { nodes, edges } = await counts(page);
		expect(nodes).toBe(0);
		expect(edges).toBe(0);
	});
});
