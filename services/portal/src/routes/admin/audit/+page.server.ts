import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

/**
 * The audit log became the observability view, which shows the same events with
 * the fields they actually carry. Kept as a redirect so existing links and
 * bookmarks land somewhere useful instead of 404ing.
 */
export const load: PageServerLoad = async ({ url }) => {
	const params = new URLSearchParams(url.search);
	throw redirect(308, `/admin/observability${params.size ? '?' + params : ''}`);
};
